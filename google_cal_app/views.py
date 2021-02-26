# Copyright 2020 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The view layer of logic for the BM gCal Assistant.

The logic here defines the behavior of the webhook when messages are received
from users messaging through Business Messages.
"""

import base64
import datetime
import hashlib
import json
import os
import uuid

from businessmessages import businessmessages_v1_client as bm_client
from businessmessages.businessmessages_v1_messages import (
    BusinessmessagesConversationsMessagesCreateRequest,
    BusinessMessagesMessage, BusinessMessagesRepresentative,
    BusinessMessagesSuggestion, BusinessMessagesSuggestedReply,
    BusinessmessagesConversationsEventsCreateRequest, BusinessMessagesEvent,
    BusinessMessagesAuthenticationRequest, BusinessMessagesAuthenticationRequestOauth
)
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from google_cal_app.models import Conversation
from googleapiclient.discovery import build
from oauth2client import client
from oauth2client.service_account import ServiceAccountCredentials

import requests

# The location of the service account credentials
SERVICE_ACCOUNT_LOCATION = 'resources/bm-agent-service-account-credentials.json'

# Set of commands the bot understands
CMD_LOGIN = 'login'
CMD_MY_DAY_SUMMARY = 'day-summary'

CMD_FOCUS_SPRINT_SLOTS = 'focus-sprints'
CMD_CANCEL_ALL_MEETINGS = 'cancel-all-meetings'

CMD_YES_CANCEL = 'yes-cancel'
CMD_NO_CANCEL = 'no-do-not-cancel'

# The representative type that all messages are sent as
BOT_REPRESENTATIVE = BusinessMessagesRepresentative(
    representativeType=BusinessMessagesRepresentative
    .RepresentativeTypeValueValuesEnum.BOT,
    displayName='BM gCal Assistant',
    avatarImage='https://lh3.googleusercontent.com/9PMLInqtfgnRnV-9QUgYj8W-ZAutv-49KsYmHthZayM9YnCsd01P0eNhbqtu9QoIF31tKzgwo-x1oCkVIQas5Q'
)

LARGE_DATE = datetime.datetime(9999, 12, 30, 12, 59, 59, 59)
DATE_FORMAT = '%Y-%m-%dT%H:%M:%S'


@csrf_exempt
def callback(request):
  """Callback URL.

  Processes messages sent from the user.

  Args:
      request (HttpRequest): The request object that django passes to the
        function

  Returns:
      An :HttpResponse: containing browser renderable HTML.
  """

  if request.method == 'POST':
    request_data = request.body.decode('utf8').replace("'", '"')
    request_body = json.loads(request_data)

    print('request_body: %s', request_body)

    # Extract the conversation id and message text
    conversation_id = request_body.get('conversationId')
    conv = get_conversation(conversation_id)

    print('conversation_id: %s', conversation_id)

    try:
      display_name = request_body.get('context').get('userInfo').get(
          'displayName')

    except Exception as e:
      print(e)
      display_name = None

    # Check that the message and text body exist

    if 'message' in request_body and 'text' in request_body['message']:
      message = request_body['message']['text']
      print('message: %s', message)
      route_message(message, conv)

    elif 'suggestionResponse' in request_body:
      message = request_body['suggestionResponse']['postbackData']
      print('message: %s', message)
      route_message(message, conv)

    elif 'authenticationResponse' in request_body:
      try:
        auth_code = request_body.get('authenticationResponse').get('code')
        redirect_uri = request_body.get('authenticationResponse').get('redirectUri')

        print(f'redirect_uri extracted from authenticationResponse {redirect_uri}')

        # Exchange auth_code with OAuth provider and get access_token
        code_verifier = conv.code_verifier

        if code_verifier is None or auth_code is None:
          print('There was an error.')
        else:
          access_token = request_access_token(auth_code, code_verifier, redirect_uri)

          # Save the access token in an encrypted format using save_token
          send_day_summary_message(conv, access_token)

      except Exception as e:
        print(f'Login error: {e}')

    elif 'userStatus' in request_body:
      if 'isTyping' in request_body['userStatus']:
        print('User is typing')
      elif 'requestedLiveAgent' in request_body['userStatus']:
        print('User requested transfer to live agent')

    return HttpResponse('Response.')

  return HttpResponse('This webhook expects a POST request.')


def request_access_token(auth_code, code_verifier, redirect_uri):
  """Requests access_token from identity provider.

  Args:
      auth_code (str): Authorization code to request access_token
      code_verifier (str): pair of code_challenge and code_verifier for PKCE.
  """

  obj = {
      'client_secret': os.environ['OAUTH_CLIENT_SECRET'],
      'client_id': os.environ['OAUTH_CLIENT_ID'],
      'grant_type': 'authorization_code',
      'code': auth_code,
      'code_verifier': code_verifier,
      'redirect_uri': redirect_uri
  }

  res = requests.post('https://oauth2.googleapis.com/token', data=obj)

  res_dict = json.loads(res.text)
  access_token = res_dict.get('access_token')

  if access_token is None:
    print(f'Could not find the access token: {res.content}')
    return None

  print(f'We found the access_token.')
  return access_token

def get_conversation(conversation_id):
  """Returns a google_cal_app.Conversation object.

  Args:
      conversation_id (str): The unique id for this user and agent.
  """
  conv = Conversation.objects.filter(id=conversation_id)
  if not conv:
    return Conversation(id=conversation_id).save()
  else:
    return conv[0]


def route_message(message, conv):
  """Routes the message received from the user to create a response.

  Args:
      message (str): The message text received from the user.
      conv (Conversation): The unique id for this user and agent.
  """
  normalized_message = message.lower()

  print(f'Routing message: {normalized_message}')

  if normalized_message == CMD_LOGIN:
    invoke_login_chip(conv)
  else:
    echo_message(message, conv)


def fetch_events(access_token, today):
  """Fetches events from Calendar API.

  Args:
      access_token (str): The user's access_token to query data with.
      today (datetime.Date): Date object representing todays date.

  Returns:
      event_items (list): A list of sorted event items.
  """
  credentials = client.AccessTokenCredentials(
      access_token, 'USER_AGENT')
  service = build('calendar', 'v3', credentials=credentials)

  events = service.events().list(
      calendarId='primary',
      timeMax=f'{today}T23:59:59-07:00',
      timeMin=f'{today}T06:00:00-07:00').execute()

  event_items = events.get('items')

  event_items.sort(
      key=lambda x: LARGE_DATE
      if (x.get('start') is None or x.get('start').get('dateTime') is None)
        else datetime.datetime.strptime(
          x.get('start').get('dateTime')[:19], DATE_FORMAT))
  print("Returning")
  return event_items


def send_day_summary_message(conv, access_token):
  """Fetches calendar data with access_token and sends it to the conversation.

  Args:
      conv (Conversation): The unique id for this user and agent.
  """

  try:
    print("Send summary of my day")
    today = str(datetime.datetime.now().date())
    event_items = fetch_events(access_token, today)
    print(f"Events: {event_items}")
    event_set = set()
    event_list_message = ''

    for event in event_items:
      try:
        if event.get('status') == 'confirmed' and today in event.get(
            'start').get('dateTime') and event.get(
                'summary') not in event_set:

          event_list_message = event_list_message + '- ' + event.get(
              'summary') + '\n'
          event_set.add(event.get('summary'))

      except Exception as e:
        print(f'Exception A: {e}')

    if len(event_set) > 4:
      message_obj = BusinessMessagesMessage(
          messageId=str(uuid.uuid4().int),
          representative=BOT_REPRESENTATIVE,
          text='Looks like you have a lot of meetings today!')

      send_message(message_obj, conv.id)

    message_obj = BusinessMessagesMessage(
        messageId=str(uuid.uuid4().int),
        representative=BOT_REPRESENTATIVE,
        text='Here\'s the list of items or your calendar...')

    send_message(message_obj, conv.id)

    message_obj = BusinessMessagesMessage(
        messageId=str(uuid.uuid4().int),
        representative=BOT_REPRESENTATIVE,
        suggestions=get_suggestions(),
        text=event_list_message)

    send_message(message_obj, conv.id)

  except Exception as e:
    print(f'Exception B: {e}')


def invoke_login_chip(conv, message=None):
  """Invokes the login chip within the conversation.

  Args:
      conv (Conversation): The unique id for this user and agent.
      message (str): The message text received from the user.
  """
  message = message or 'To see your calendar summary, please sign in!'
  message_id = str(uuid.uuid4())

  # Generate a code_verifier and code_challenge used in the OAuth 2.0 PKCE flow.
  # code_challenge is shared with Google to send to kick start the auth flow
  # with the identity provider. Then exchange the auth_code along with the
  # code_verifier to the identity provider to get an access_token to make
  # requests on behalf of the user.
  random_val = str(uuid.uuid1()).encode()
  base64_random = base64.urlsafe_b64encode(random_val)
  code_verifier = base64_random.decode('utf-8')

  hashed_code_verifier = hashlib.sha256(code_verifier.encode('utf-8')).digest()
  utf8_decoded_verifier = base64.urlsafe_b64encode(hashed_code_verifier).decode(
      'utf-8')
  code_challenge = utf8_decoded_verifier.replace('=', '')

  message_obj = BusinessMessagesMessage(
      messageId=str(uuid.uuid4().int),
      representative=BOT_REPRESENTATIVE,
      suggestions=get_auth_chip_suggestion(
          os.environ['OAUTH_CLIENT_ID'],
          code_challenge,
          ['profile','https://www.googleapis.com/auth/calendar.readonly']),
      text=message,
      fallback='Your device does not support suggestions')

  send_message(message_obj, conv.id)

  print(f'The code verifier is: {code_verifier}')
  conv.code_verifier = code_verifier
  conv.save()


def echo_message(message, conv):
  """Sends the message received from the user back to the user.

  Args:
      message (str): The message text received from the user.
      conv (Conversation): The unique id for this user and agent.
  """

  message_obj = BusinessMessagesMessage(
      messageId=str(uuid.uuid4().int),
      representative=BOT_REPRESENTATIVE,
      text=f"Hey! Here's the message you sent:\n\n{message}"
  )

  send_message(message_obj, conv.id)


def send_message(message, conversation_id):
  """Posts a message to the Business Messages API.

  Args:
      message (obj): The message object payload to send to the user.
      conversation_id (str): The unique id for this user and agent.
  """

  credentials = ServiceAccountCredentials.from_json_keyfile_name(
      SERVICE_ACCOUNT_LOCATION,
      scopes=['https://www.googleapis.com/auth/businessmessages'])

  bm_credentials = bm_client.BusinessmessagesV1(credentials=credentials)

  # Send the typing started event
  create_request = BusinessmessagesConversationsEventsCreateRequest(
      eventId=str(uuid.uuid4().int),
      businessMessagesEvent=BusinessMessagesEvent(
          representative=BOT_REPRESENTATIVE,
          eventType=BusinessMessagesEvent.EventTypeValueValuesEnum.TYPING_STARTED
      ),
      parent='conversations/' + conversation_id)

  bm_client.BusinessmessagesV1.ConversationsEventsService(
      client=bm_credentials).Create(request=create_request)

  # Create the message request
  create_request = BusinessmessagesConversationsMessagesCreateRequest(
      businessMessagesMessage=message,
      parent='conversations/' + conversation_id)

  bm_client.BusinessmessagesV1.ConversationsMessagesService(
      client=bm_credentials).Create(request=create_request)

  # Send the typing stopped event
  create_request = BusinessmessagesConversationsEventsCreateRequest(
      eventId=str(uuid.uuid4().int),
      businessMessagesEvent=BusinessMessagesEvent(
          representative=BOT_REPRESENTATIVE,
          eventType=BusinessMessagesEvent.EventTypeValueValuesEnum.TYPING_STOPPED
      ),
      parent='conversations/' + conversation_id)

  bm_client.BusinessmessagesV1.ConversationsEventsService(
      client=bm_credentials).Create(request=create_request)


def get_auth_chip_suggestion(client_id, code_challenge, scopes):
  """Returns an authorization chip

  Arguments:
      client_id (str): client_id from your client configuration with the
          identity provider
      code_challenge (str): code_challenge generated from the code_verifier for
          use with PKCE in OAuth 2.0 access_token exchange
      scopes (List): A list of scopes you want the access token to grant API
          access to
  Returns:
      A :list: BusinessMessagesSuggestions invoking the auth chip
  """
  return [
      BusinessMessagesSuggestion(
        authenticationRequest=BusinessMessagesAuthenticationRequest(
            oauth=BusinessMessagesAuthenticationRequestOauth(
                clientId=client_id, codeChallenge=code_challenge, scopes=scopes))),
  ]


def get_suggestions():
  """Creates a list of suggestions.

  Returns:
    A :list: A list of sample BusinessMessagesSuggestions.
  """
  return [
      BusinessMessagesSuggestion(
          reply=BusinessMessagesSuggestedReply(
              text='Let\'s do it again!', postbackData=CMD_LOGIN)),
  ]


def landing_placeholder(request):
  """Creates an HttpResponse for a web request at the root of the project.

  Args:
      request (HttpRequest): The django web request object

  Returns:
      An :HttpResponse: containing browser renderable HTML.
  """

  return HttpResponse("""
  <h1>Welcome to gCal BM Assistant</h1>
  <br/><br/>
  Check out the <a href="https://business-communications.sandbox.google.com/console/">
  Business Communications Developer Console</a> to access this agent's
  test URLs.
  """)
