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

'''
Utility to send messages using the command line
'''

from django.core.management.base import BaseCommand, CommandError
from google_cal_app.models import *
from google_cal_app.views import *

class Command(BaseCommand):
    help = 'Send a message through gCalBot CLI'

    def add_arguments(self, parser):
        parser.add_argument('conversation_id', nargs='+', type=str)
        parser.add_argument('message', nargs='+', type=str)

    def handle(self, *args, **options):
        conversation_id = options['conversation_id'][0]
        message = options['message'][0]

        route_message(message, Conversation.objects.get(id=conversation_id))