#!/usr/bin/env python

from flask import Flask, request, session, redirect, url_for, flash, make_response
from flask import render_template, render_template_string
from stravalib import Client
from config import SECRET_KEY, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_CALLBACK_URL

app = Flask(__name__)
app.config.from_object(__name__)

@app.route('/')
def index():
    return "<html><body>index</body></html>"

@app.route('/login')
def login():
    if session.get('access_token', None) is None:
        return redirect(Client().authorization_url(client_id=STRAVA_CLIENT_ID, redirect_uri=STRAVA_CALLBACK_URL, scope="view_private"))
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    return redirect(url_for('index'))

@app.route('/auth')
def auth():
    client = Client()
    code = request.args.get('code')
    token = Client().exchange_code_for_token(client_id=STRAVA_CLIENT_ID, client_secret=STRAVA_CLIENT_SECRET, code=code)
    if token:
        session['access_token'] = token
    return redirect(url_for('athlete'))

@app.route('/athlete')
def athlete():
    token = session.get('access_token', None)
    if token is None:
        return redirect(url_for('login'))
    client = Client(token)
    athlete = client.get_athlete()
    activities = client.get_activities(limit=10)
    response = make_response(
      render_template('athlete.html',
                  athlete=athlete,
                  ACTIVITIES=activities))
    response.headers['Content-Type'] = 'text/html'
    return response


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
