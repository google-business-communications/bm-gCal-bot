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

"""
Model definitions for persistested data in gCal BM Assistant Sample.
"""

from django.db import models
from cryptography.fernet import Fernet
import gcalbot.settings as settings

class Conversation(models.Model):
  '''
  A class to represent a conversation tied to a user.
  '''

  def __str__(self):
    return f"{self.id}"

  id = models.CharField(max_length=64, unique=True, primary_key=True)
  code_verifier = models.CharField(max_length=128, default=None, blank=True, null=True)

class Feedback(models.Model):
  '''
  A Django model extension to tracks anonymous feedback.
  '''

  text = models.TextField()
  reviewed = models.BooleanField(default=False)
