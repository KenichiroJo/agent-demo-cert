# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import pulumi_datarobot

MCP_USER_RUNTIME_PARAMETERS: list[
    pulumi_datarobot.CustomModelRuntimeParameterValueArgs
] = [
    pulumi_datarobot.CustomModelRuntimeParameterValueArgs(
        key="user_name",
        type="string",
        value=os.getenv("USER_NAME", "default-user"),
    ),
    pulumi_datarobot.CustomModelRuntimeParameterValueArgs(
        key="FORECAST_DEPLOYMENT_ID",
        type="string",
        value=os.getenv("FORECAST_DEPLOYMENT_ID", ""),
    ),
    pulumi_datarobot.CustomModelRuntimeParameterValueArgs(
        key="SCORING_DATASET_ID",
        type="string",
        value=os.getenv("SCORING_DATASET_ID", ""),
    ),
    pulumi_datarobot.CustomModelRuntimeParameterValueArgs(
        key="VDB_DEPLOYMENT_ID",
        type="string",
        value=os.getenv("VDB_DEPLOYMENT_ID", ""),
    ),
]
