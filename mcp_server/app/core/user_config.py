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

from typing import Any, Optional

from datarobot_genai.drmcp import (
    RUNTIME_PARAM_ENV_VAR_NAME_PREFIX,
    extract_datarobot_runtime_param_payload,
)
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class UserAppConfig(BaseSettings):
    """User-specific application configuration."""

    # Example of adding user-specific configuration
    user_name: str = Field(
        default="default-user",
        validation_alias=AliasChoices(
            RUNTIME_PARAM_ENV_VAR_NAME_PREFIX + "USER_NAME",
            "USER_NAME",
        ),
        description="Name of the user being used",
    )

    # 小売EC売上予測エージェント設定
    forecast_deployment_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            RUNTIME_PARAM_ENV_VAR_NAME_PREFIX + "FORECAST_DEPLOYMENT_ID",
            "FORECAST_DEPLOYMENT_ID",
        ),
        description="DataRobot時系列予測モデルのデプロイメントID",
    )
    scoring_dataset_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            RUNTIME_PARAM_ENV_VAR_NAME_PREFIX + "SCORING_DATASET_ID",
            "SCORING_DATASET_ID",
        ),
        description="スコアリング用データセットのID",
    )
    vdb_deployment_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            RUNTIME_PARAM_ENV_VAR_NAME_PREFIX + "VDB_DEPLOYMENT_ID",
            "VDB_DEPLOYMENT_ID",
        ),
        description="VectorDatabase（PDF RAG）のデプロイメントID",
    )

    @field_validator(
        "user_name",
        "forecast_deployment_id",
        "scoring_dataset_id",
        "vdb_deployment_id",
        mode="before",
    )
    @classmethod
    def validate_user_runtime_params(cls, v: Any) -> Any:
        """Validate user runtime parameters."""
        return extract_datarobot_runtime_param_payload(v)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global configuration instance
_user_config: Optional[UserAppConfig] = None


def get_user_config() -> UserAppConfig:
    """Get the global user configuration instance."""
    global _user_config
    if _user_config is None:
        _user_config = UserAppConfig()
    return _user_config
