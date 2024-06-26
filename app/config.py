from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_source: str = './data/chek-profiles.ttl'


settings = Settings()