from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_source: str = './data/chek-profiles.ttl'
    val3dity: str = '/opt/val3dity/val3dity'
    citygml_tools: str = '/opt/citygml-tools/citygml-tools'
    temp_dir: str = './tmp'


settings = Settings()
