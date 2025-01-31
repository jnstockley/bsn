# create a peewee database instance -- our models will use this database to
# persist information
from peewee import Model, CharField, IntegerField
from models import database


class BaseModel(Model):
    class Meta:
        database = database


class YouTubeChannel(BaseModel):
    id = CharField(primary_key=True, unique=True, null=False)
    num_videos = IntegerField(null=False)
