# Generated by Django 3.0.8 on 2020-11-04 06:46

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
Autogenerated migrations from models.py.
'''
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('google_cal_app', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversation',
            name='access_token',
            field=models.BinaryField(blank=True, default=None, null=True),
        ),
    ]
