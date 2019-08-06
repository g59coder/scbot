# -*- encoding: utf-8 -*-
import configparser
import math
import os
import re
import shutil
import tempfile
import time
from datetime import datetime

import mutagen
import requests
from clint.textui import progress
import telebot

CLIENT_ID = 'a3e059563d7fd3372b49b37f00a00bcf'
ALT_CLIENT_ID = '2t9loNQH90kzJcsFCODdigxfp325aq4z'
ALT2_CLIENT_ID = 'NONE'
TOKEN = '847690058:AAEWV6k3-etwNDGa-mUNyVsg4sD1qa-AozE'


def get_collection(url, token):
    params = {
        'client_id': CLIENT_ID,
        'linked_partitioning': '1',
    }
    if token:
        params['oauth_token'] = token
    resources = list()
    while url:
        response = requests.get(url, params=params)
        response.raise_for_status()
        json_data = response.json()
        if 'collection' in json_data:
            resources.extend(json_data['collection'])
        else:
            resources.extend(json_data)
        if 'next_href' in json_data:
            url = json_data['next_href']
        else:
            url = None
    return resources


arguments = None
token = ''
path = ''
offset = 1

url = {
    'playlists-liked': ('https://api-v2.soundcloud.com/users/{0}/playlists'
                        '/liked_and_owned?limit=200'),
    'favorites': ('https://api.soundcloud.com/users/{0}/favorites?'
                  'limit=200'),
    'commented': ('https://api.soundcloud.com/users/{0}/comments'),
    'tracks': ('https://api.soundcloud.com/users/{0}/tracks?'
               'limit=200'),
    'all': ('https://api-v2.soundcloud.com/profile/soundcloud:users:{0}?'
            'limit=200'),
    'playlists': ('https://api.soundcloud.com/users/{0}/playlists?'
                  'limit=5'),
    'resolve': ('https://api.soundcloud.com/resolve?url={0}'),
    'trackinfo': ('https://api.soundcloud.com/tracks/{0}'),
    'user': ('https://api.soundcloud.com/users/{0}'),
    'me': ('https://api.soundcloud.com/me?oauth_token={0}')
}

fileToKeep = []


def get_config():
    global token
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.expanduser('~'), '.config/scdl/scdl.cfg'))
    try:
        token = config['scdl']['auth_token']
        path = config['scdl']['path']
    except:
        pass
    if os.path.exists(path):
        os.chdir(path)


def get_item(track_url, client_id=CLIENT_ID):
    try:
        item_url = url['resolve'].format(track_url)
        r = requests.get(item_url, params={'client_id': client_id})
        if r.status_code == 403:
            return get_item(track_url, ALT_CLIENT_ID)

        item = r.json()
        no_tracks = item['kind'] == 'playlist' and not item['tracks']
        if no_tracks and client_id != ALT_CLIENT_ID:
            return get_item(track_url, ALT_CLIENT_ID)
    except Exception:
        if client_id == ALT_CLIENT_ID:
            return
        time.sleep(5)
        try:
            return get_item(track_url, ALT_CLIENT_ID)
        except Exception as e:
            pass
    return item


def parse_url(track_url, chat_id=None):
    item = get_item(track_url)
    if not item:
        return
    elif item['kind'] == 'track':
        # logger.info('Found a track')
        download_track(item, chat_id=chat_id)
    elif item['kind'] == 'playlist':
        # logger.info('Found a playlist')
        download_playlist(item, chat_id=chat_id)
    elif item['kind'] == 'user':
        download(item, 'all', 'tracks and reposts', chat_id=chat_id)


def who_am_i():
    me = url['me'].format(token)
    r = requests.get(me, params={'client_id': CLIENT_ID})
    r.raise_for_status()
    current_user = r.json()
    return current_user


def remove_files(file_list):
    files = [f for f in os.listdir('.') if os.path.isfile(f)]
    for f in files:
        if f in file_list:
            os.remove(f)


def get_track_info(track_id):
    info_url = url["trackinfo"].format(track_id)
    r = requests.get(info_url, params={'client_id': CLIENT_ID}, stream=True)
    item = r.json()
    return item


def download(user, dl_type, dl_type2, chat_id=None):
    username = user['username']
    user_id = user['id']
    dl_url = url[dl_type].format(user_id)
    resources = get_collection(dl_url, token)
    del resources[:offset - 1]
    total = len(resources)
    for counter, item in enumerate(resources, offset):
        try:
            if dl_type == 'all':
                item_name = item['type'].split('-')[0]
                uri = item[item_name]['uri']
                parse_url(uri, chat_id=chat_id)
            elif dl_type == 'playlists':
                download_playlist(item, chat_id=chat_id)
            elif dl_type == 'playlists-liked':
                parse_url(item['playlist']['uri'], chat_id=chat_id)
            elif dl_type == 'commented':
                item = get_track_info(item['track_id'])
                download_track(item, chat_id=chat_id)
            else:
                download_track(item, chat_id=chat_id)
        except Exception as e:
            pass


def download_playlist(playlist, chat_id=None):
    global fileToKeep
    invalid_chars = '\/:*?|<>"'
    playlist_name = playlist['title'].encode('utf-8', 'ignore')
    playlist_name = playlist_name.decode('utf8')
    playlist_name = ''.join(c for c in playlist_name if c not in invalid_chars)

    try:
        del playlist['tracks'][:offset - 1]
        for counter, track_raw in enumerate(playlist['tracks'], offset):
            download_track(track_raw, playlist['title'], chat_id=chat_id)
    except:
        fileToKeep = fileToKeep[:-1]
        bot.send_message(chat_id, "Не удалось скачать плейлист")
        bot.send_message(chat_id, "Попробуйте скачать каждую песню отдельно")
    finally:
        os.chdir('..')


def try_utime(path, filetime):
    try:
        os.utime(path, (time.time(), filetime))
    except:
        pass


def get_filename(track, original_filename=None):
    invalid_chars = '\/:*?|<>"'
    username = track['user']['username']
    title = track['title'].encode('utf-8', 'ignore').decode('utf8')

    ext = ".mp3"
    if original_filename is not None:
        original_filename.encode('utf-8', 'ignore').decode('utf8')
        ext = os.path.splitext(original_filename)[1]
    filename = title[:251] + ext.lower()
    filename = ''.join(c for c in filename if c not in invalid_chars)
    return filename


def download_track(track, playlist_name=None, playlist_file=None, chat_id=None):
    title = track['title']
    title = title.encode('utf-8', 'ignore').decode('utf8')

    if not track['streamable']:
        return

    r = None

    if track['downloadable']:
        original_url = track['download_url']
        r = requests.get(
            original_url, params={'client_id': CLIENT_ID}, stream=True
        )
        if r.status_code == 401:
            filename = get_filename(track)
        else:
            d = r.headers.get('content-disposition')
            filename = re.findall("filename=(.+)", d)[0][1:-1]
            filename = get_filename(track, filename)

    else:
        filename = get_filename(track)

    if playlist_file:
        duration = math.floor(track['duration'] / 1000)
        playlist_file.write(
            '#EXTINF:{0},{1}{3}{2}{3}'.format(
                duration, title, filename, os.linesep
            )
        )

    fileToKeep.append(filename)

    if r is None or r.status_code == 401:
        url = track['stream_url']
        r = requests.get(url, params={'client_id': CLIENT_ID}, stream=True)
        # logger.debug(r.url)
        if r.status_code == 401 or r.status_code == 429:
            r = requests.get(
                url, params={'client_id': ALT_CLIENT_ID}, stream=True
            )
            r.raise_for_status()
    temp = tempfile.NamedTemporaryFile(delete=False)

    total_length = int(r.headers.get('content-length'))

    received = 0
    with temp as f:
        for chunk in progress.bar(
                r.iter_content(chunk_size=1024),
                expected_size=(total_length / 1024) + 1,
                hide=False
        ):
            if chunk:
                received += len(chunk)
                f.write(chunk)
                f.flush()

    if received != total_length:
        return 0

    shutil.move(temp.name, os.path.join(os.getcwd(), filename))

    if filename.endswith('.mp3') or filename.endswith('.flac'):
        try:
            set_metadata(track, filename, playlist_name)
        except Exception as e:
            pass

    created_at = track['created_at']
    timestamp = datetime.strptime(created_at, '%Y/%m/%d %H:%M:%S %z')
    filetime = int(time.mktime(timestamp.timetuple()))
    try_utime(filename, filetime)

    audio = open(fileToKeep[0], 'rb')
    bot.send_audio(chat_id, audio)
    audio.close()
    remove_files([fileToKeep.pop()])


def can_convert(filename):
    ext = os.path.splitext(filename)[1]
    return 'wav' in ext or 'aif' in ext


def in_download_archive(track):
    global arguments
    if not arguments['--download-archive']:
        return

    archive_filename = arguments.get('--download-archive')
    try:
        with open(archive_filename, 'a+', encoding='utf-8') as file:
            file.seek(0)
            track_id = '{0}'.format(track['id'])
            for line in file:
                if line.strip() == track_id:
                    return True
    except IOError as ioe:
        pass

    return False


def set_metadata(track, filename, album=None):
    artwork_url = track['artwork_url']
    user = track['user']
    if not artwork_url:
        artwork_url = user['avatar_url']
    artwork_url = artwork_url.replace('large', 't500x500')
    response = requests.get(artwork_url, stream=True)
    with tempfile.NamedTemporaryFile() as out_file:
        shutil.copyfileobj(response.raw, out_file)
        out_file.seek(0)

        track_created = track['created_at']
        track_date = datetime.strptime(track_created, "%Y/%m/%d %H:%M:%S %z")
        debug_extract_dates = '{0} {1}'.format(track_created, track_date)
        track['date'] = track_date.strftime("%Y-%m-%d %H::%M::%S")

        track['artist'] = user['username']

        audio = mutagen.File(filename, easy=True)
        audio['title'] = track['title']
        audio['artist'] = track['artist']
        if album: audio['album'] = album
        if track['genre']: audio['genre'] = track['genre']
        if track['permalink_url']: audio['website'] = track['permalink_url']
        if track['date']: audio['date'] = track['date']
        audio.save()

        a = mutagen.File(filename)
        if track['description']:
            if a.__class__ == mutagen.flac.FLAC:
                a['description'] = track['description']
            elif a.__class__ == mutagen.mp3.MP3:
                a['COMM'] = mutagen.id3.COMM(
                    encoding=3, lang=u'ENG', text=track['description']
                )
        if artwork_url:
            if a.__class__ == mutagen.flac.FLAC:
                p = mutagen.flac.Picture()
                p.data = out_file.read()
                p.width = 500
                p.height = 500
                p.type = mutagen.id3.PictureType.COVER_FRONT
                a.add_picture(p)
            elif a.__class__ == mutagen.mp3.MP3:
                a['APIC'] = mutagen.id3.APIC(
                    encoding=3, mime='image/jpeg', type=3,
                    desc='Cover', data=out_file.read()
                )
        a.save()


bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=['start'])
def send_hi(message):
    bot.send_message(message.chat.id, "Я готов!")


@bot.message_handler(content_types=['text'])
def echo_all(message):
    desired_row = 'https://soundcloud.com/'
    if desired_row in message.text:
        url_pos = message.text.find(desired_row)
        if url_pos is not False:
            bot.reply_to(message, "Скачиваю...")
            parse_url(message.text[url_pos::], chat_id=message.chat.id)
            bot.send_message(message.chat.id, "Приятного прослушивания😊")


bot.polling(none_stop=True)
