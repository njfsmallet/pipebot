import boto3
from pipebot.config import AppConfig

def create_bedrock_client(app_config: AppConfig, debug=False):
    bedrock_session = boto3.Session(profile_name='default')
    return bedrock_session.client(
        service_name='bedrock-runtime',
        region_name=app_config.aws.region_name,
        config=boto3.session.Config(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            read_timeout=1000,
            tcp_keepalive=False
        )
    ) 