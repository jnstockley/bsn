# create a peewee database instance -- our models will use this database to
# persist information
from peewee import Model, CharField, IntegerField, TextField, DateTimeField, AutoField
from models import database


class BaseModel(Model):
    class Meta:
        database = database


class YouTubeChannel(BaseModel):
    id = CharField(primary_key=True, unique=True, null=False)
    num_videos = IntegerField(null=False)


class OAuthCredentials(BaseModel):
    id = AutoField()
    client_id = CharField(null=True)
    client_secret = TextField(null=True)
    user_id = CharField(null=True)
    user_email = CharField(null=True)
    access_token = TextField(null=True)
    refresh_token = TextField(null=True)
    token_uri = TextField(null=True)
    scopes = TextField(null=True)
    token_type = CharField(null=True)
    expiry = DateTimeField(null=True)
    extra = TextField(null=True)

    class Meta:
        table_name = "oauth_credentials"
