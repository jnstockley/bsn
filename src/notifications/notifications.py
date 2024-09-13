from apprise import apprise

from notifications import apprise_urls


def send_youtube_channels_notifications(channels: list[dict]):
    apobj = apprise.Apprise()

    for apprise_url in apprise_urls:
        apobj.add(apprise_url)

    if len(channels) > 1:
        title = f"{','.join([channel['snippet']['title'] for channel in channels])} have uploaded new videos to YouTube!"
        body = "Check them out here: https://www.youtube.com/feed/subscriptions"
    else:
        title = f"{channels[0]['snippet']['title']} has uploaded a new video to YouTube!"
        body = f"Check it out here: https://www.youtube.com/channel/{channels[0]['id']}"

    apobj.notify(title=title, body=body)
