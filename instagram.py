from __builtin__ import classmethod
import json
import os
import random
import re

from google.appengine.api import users, urlfetch
from google.appengine.ext import ndb
import webapp2

import jinja2 as _jinja2


jinja = _jinja2.Environment(
    loader=_jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

INSTAGRAM_URL = "https://api.instagram.com/v1/tags/%s/media/recent?access_token=%s"
TOKEN_PATTERN = re.compile(r"([^a-zA-Z0-9.])")

class InstagramData(ndb.Model):
    content = ndb.TextProperty()
    url = ndb.TextProperty()
    token = ndb.TextProperty()

    date = ndb.DateTimeProperty(auto_now=True)

    @classmethod
    def get_latest_content(cls):
        query = cls.query()
        query = query.order(-cls.date)
        latest = query.get()
        return latest.content if latest else None

    @classmethod
    def save_data(cls, content, token, url):
        d = cls(content=content, token=token, url=url)
        d.put()

class InstagramToken(ndb.Model):
    token = ndb.StringProperty(indexed=False)

    @classmethod
    def get_random(cls):
        tokens = cls.get_all()
        return random.choice(tokens) if tokens else None

    @classmethod
    def set_tokens(cls, tokens):
        # XXX: To keep it simple, just delete all and recreate
        ndb.delete_multi(cls.query().fetch(keys_only=True))
        for t in tokens:
            token = cls(token=t)
            token.put()

    @classmethod
    def get_all(cls):
        query = cls.query()
        # query = query.filter(cls.valid == True)
        tokens = [t.token for t in query.fetch()]
        return tokens

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.redirect("/content/index.html")

class Admin(webapp2.RequestHandler):
    def get(self):
        return self.handle_request()

    def post(self):
        return self.handle_request()

    def handle_request(self):
        user = users.get_current_user()

        if user and users.is_current_user_admin():
            return self.admin_page()
        else:
            return self.login_page()

    def login_page(self):
        self.redirect(users.create_login_url(self.request.uri))

    def admin_page(self):
        tokens = []
        if self.request.method == "POST":
            tokens = self.request.get("tokens")
            tokens = [TOKEN_PATTERN.sub("", t) for t in tokens.split("\n")]
            tokens = filter(lambda t: t, tokens)
            InstagramToken.set_tokens(tokens)
        else:
            tokens = InstagramToken.get_all()

        tokens_flat = "\n".join(tokens)
        user = users.get_current_user()
        logout_url = users.create_logout_url(self.request.uri)
        self.response.write(jinja.get_template("templates/admin.html").render(locals()))

class UpdateTask(webapp2.RequestHandler):
    def get(self):
        token = InstagramToken.get_random()
        if token is None:
            self.response.set_status(500)
            self.response.headers['Content-Type'] = 'text/txt; charset=utf-8'
            self.response.write("No tokens available")
            return

        url = INSTAGRAM_URL % ("araripina", token)
        result = urlfetch.fetch(url)
        self.response.headers['Content-Type'] = 'application/json;charset=utf-8'
        self.response.write(result.content)
        self.response.set_status(result.status_code)
        if result.status_code == 200:
            # save
            InstagramData.save_data(result.content, token, url)


class DataPage(webapp2.RequestHandler):
    def get(self):
        content = InstagramData.get_latest_content()
        if not content:
            self.response.set_status(204)
        else:
            self.response.headers['Content-Type'] = 'application/json;charset=utf-8'
            self.response.write(content)

class Playlist(webapp2.RequestHandler):
    OFFLINE = "http://192.168.0.116:8080/content/offline.html"
    PING = "http://tv.araripina.com.br/service/service/salva/%s"
    INSTAGRAM = "http://192.168.0.116:8080/content/index.html"
    MAIN = "http://tv.araripina.com.br/%s"
    def get(self, name):
        self.response.headers['Content-Type'] = 'application/json;charset=utf-8'

        data = dict()
        data['offline'] = self.OFFLINE
        data['ping'] = self.PING % (name,)
        data['playlist'] = playlist = list()
        playlist.append({'url': self.MAIN % (name,), 'duration': '60'})
        playlist.append({'url': self.INSTAGRAM, 'duration': '60'})

        self.response.write(json.dumps(data))



app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/data', DataPage),
    ('/admin', Admin),
    webapp2.Route('/api/playlist/<name>', Playlist),
    ('/tasks/update', UpdateTask)
], debug=True)
