# updatebky.py
# Author: Richard Gibson
#
# Handles updates to the best known times.  Games are specified through the 
# URL, while categories are specified through the 'c' query parameter.  
# Currently, updates can be made by anyone who has run the game, and any 
# update that fills in the necessary inputs is valid.  This means that 
# malicious users could really cause problems if they wanted to by overwriting
# best known times with worse times, but I'm putting a bit of trust on the 
# users here.  If something like this becomes a problem, I'll have to cross 
# that bridge and come up with a better solution here.
#

import util
import logging
import games
import json
import handler

class UpdateBkt( handler.Handler ):
    def get( self, game_code ):
        user = self.get_user( )
        if user == self.OVER_QUOTA_ERROR:
            self.error( 403 )
            self.render( "403.html" )
            return
        return_url = self.request.get( 'from' )
        if not return_url:
            return_url = "/"

        # Get the category
        category_code = self.request.get( 'c' )
        if user is None or not category_code:
            self.error( 404 )
            self.render( "404.html", user=user )
            return

        # Have to take the code of the category code because of percent
        # encoded plusses
        category_code = util.get_code( category_code )
        
        # Check to make sure that the user has run this game
        game_model = self.get_game_model( game_code )
        user_has_run = self.get_user_has_run( user.username, game_model.game )
        if not user_has_run and not user.is_mod:
            self.error( 404 )
            self.render( "404.html", user=user )
            return

        # Find the corresponding gameinfo for this category
        gameinfolist = json.loads( game_model.info )
        gameinfo = None
        for g in gameinfolist:
            if util.get_code( g['category'] ) == category_code:
                gameinfo = g
                break
        if gameinfo is None:
            self.error( 404 )
            self.render( "404.html", user=user )
            return

        params = dict( user=user, game=game_model.game, game_code=game_code, 
                       category=gameinfo['category'], return_url=return_url )
        params['username'] = gameinfo.get( 'bk_runner' )
        if params['username'] is None:
            params['username'] = ''
            params['time'] = ''
            params['datestr'] = ''
            params['video'] = ''
            params['updating'] = False
        else:
            params['time'] = util.seconds_to_timestr( 
                gameinfo.get( 'bk_seconds' ) )
            params['datestr'] = gameinfo.get( 'bk_datestr' )
            params['video'] = gameinfo.get( 'bk_video' )
            params['updating'] = True

        if return_url[ 0 : len( '/runner/' ) ] == '/runner/':
            params['from_runnerpage'] = True
        else:
            params['from_runnerpage'] = False
            
        self.render( "updatebkt.html", **params )

    def post( self, game_code ):
        user = self.get_user( )
        if user == self.OVER_QUOTA_ERROR:
            self.error( 403 )
            self.render( "403.html" )
            return
        return_url = self.request.get( 'from' )
        if not return_url:
            return_url = "/"

        # Get the category
        category_code = self.request.get( 'c' )
        if user is None or category_code is None:
            self.error( 404 )
            self.render( "404.html", user=user )
            return
        
        # Have to take the code of the category code because of percent
        # encoded plusses
        category_code = util.get_code( category_code )
        
        # Check to make sure that the user has run this game
        game_model = self.get_game_model( game_code )
        user_has_run = self.get_user_has_run( user.username, game_model.game )
        if not user_has_run and not user.is_mod:
            self.error( 404 )
            self.render( "404.html", user=user )
            return

        # Find the corresponding gameinfo for this category
        gameinfolist = json.loads( game_model.info )
        gameinfo = None
        for g in gameinfolist:
            if util.get_code( g['category'] ) == category_code:
                gameinfo = g
                break
        if gameinfo is None:
            self.error( 404 )
            self.render( "404.html", user=user )
            return

        # Get the inputs
        username = self.request.get( 'username' )
        time = self.request.get( 'time' )
        datestr = self.request.get( 'date' )
        video = self.request.get( 'video' )

        params = dict( user=user, game=game_model.game, game_code=game_code,
                       category=gameinfo['category'], username=username,
                       time=time, datestr=datestr, video=video, 
                       return_url=return_url )

        # Are we updating?
        if gameinfo.get( 'bk_runner' ) is None:
            params['updating'] = False
        else:
            params['updating'] = True

        valid = True

        # Check for where we came from
        if return_url[ 0 : len( '/runner/' ) ] == '/runner/':
            params['from_runnerpage'] = True
        else:
            params['from_runnerpage'] = False

        if not username and not time and not datestr and not video:
            gameinfo['bk_runner'] = None
            gameinfo['bk_seconds'] = None
            gameinfo['bk_datestr'] = None
            gameinfo['bk_video'] = None
            date = None
        else:
            # Make sure we got a username
            if not username:
                params['username_error'] = "You must enter a runner"
                valid = False

            # Parse the time into seconds, ensure it is valid
            ( seconds, time_error ) = util.timestr_to_seconds( time )
            if not seconds:
                params['time_error'] = "Invalid time: " + time_error
                valid = False

            # Parse the date, ensure it is valid
            ( date, date_error ) = util.datestr_to_date( datestr )
            if date_error:
                params['date_error'] = "Invalid date: " + date_error
                valid = False

            if not valid:
                self.render( "updatebkt.html", **params )
                return

            time = util.seconds_to_timestr( seconds ) # Standard format
            params['time'] = time

            # Store the best known time
            gameinfo['bk_runner'] = username
            gameinfo['bk_seconds'] = seconds
            gameinfo['bk_datestr'] = datestr
            gameinfo['bk_video'] = video

        gameinfo['bk_updater'] = user.username
        game_model.info = json.dumps( gameinfolist )
        game_model.put( )

        # Update game_model in memcache
        self.update_cache_game_model( game_code, game_model )

        # Update gamepage in memcache
        gamepage = self.get_gamepage( game_model.game, no_refresh=True )
        if gamepage is not None:
            for d in gamepage:
                if d['category'] == gameinfo['category']:
                    d['bk_runner'] = gameinfo['bk_runner']
                    d['bk_time'] = util.seconds_to_timestr( 
                        gameinfo['bk_seconds'] )
                    d['bk_date'] = date
                    d['bk_video'] = gameinfo['bk_video']
                    break
            self.update_cache_gamepage( game_model.game, gamepage )

        # All dun
        self.redirect( return_url )
