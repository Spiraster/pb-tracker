
# cleanup_games_base.py
# Author: Richard Gibson
#
# A base class that clean up games and categories from the database that no
# longer have any runs.  This can occur when someone submits a run for a new
# game or category, and then later edits or deletes the run.  Without this
# cleanup job, old games and categories will linger in the database and appear
# in the ui-autocomplete inputs on the submission page. 
#

import games
import runs
import util
import handler
import json
import logging

from google.appengine.ext import db
from google.appengine.runtime import apiproxy_errors

class CleanupGamesBase( handler.Handler ):
    def cleanup_games( self ):
        # Grab all of the categories, indexed by game
        categories = self.get_categories( )
        if categories == self.OVER_QUOTA_ERROR:
            return
        categories_modified = False

        games_to_delete = [ ]
        for game, categorylist in categories.iteritems( ):
            # Grab the game model
            game_code = util.get_code( game )
            game_model = self.get_game_model( game_code )
            if game_model == self.OVER_QUOTA_ERROR:
                return            
            gameinfolist = json.loads( game_model.info )
            game_model_modified = False
            glist = [ ( i, gameinfo ) 
                      for i, gameinfo in enumerate( gameinfolist ) ]
            for i, gameinfo in reversed( glist ):
                # Leave it if the category is marked as a base category
                if( gameinfo.get( 'is_base_category' )
                    and game != "Luigi's Mansion"
                    and game != "Super Mario Bros.: The Lost Levels"
                    and game != "The Legend of Zelda: A Link to the Past"
                    and game != "Mega Man 9" ):
                    continue
                # Check if there is a run for this game and category
                try:
                    q = db.Query( runs.Runs, keys_only=True )
                    q.ancestor( runs.key() )
                    q.filter( 'game =', game )
                    q.filter( 'category =', gameinfo['category'] )
                    num_runs = q.count( limit=1 )
                    if num_runs == 0:
                        # Remove this category
                        del gameinfolist[ i ]
                        logging.info( "Removed " + gameinfo['category'] 
                                      + " from " + game )
                        game_model_modified = True
                        # Remove this category in memcache too
                        for j, category in enumerate( categorylist ):
                            if category == gameinfo['category']:
                                del categorylist[ j ]
                                categories_modified = True
                                break
                        else:
                            logging.error( "ERROR: Could not find in "
                                           + "categories" )
                except apiproxy_errors.OverQuotaError, msg:
                    logging.error( msg )
            # Remove the game if no more categories exist
            if len( gameinfolist ) == 0:
                game_model.delete( )
                games_to_delete.append( game )
                logging.info( game + " deleted" )
                self.update_cache_game_model( game_code, None )
            # Update database and memcache if necessary
            elif game_model_modified:
                game_model.info = json.dumps( gameinfolist )
                game_model.put( )
                self.update_cache_game_model( game_code, game_model )
        
        # Finally, update categories, gamelists in memcache if necessary
        if categories_modified:
            for game in games_to_delete:
                del categories[ game ]
            self.update_cache_categories( categories )
        cached_gamelists = self.get_cached_gamelists( )
        if cached_gamelists is None:
            return
        for game in games_to_delete:
            done = False
            for page_num, res in cached_gamelists.iteritems( ):
                if done:
                    break
                for i, d in enumerate( res['gamelist'] ):
                    if d['game'] == game:
                        del( cached_gamelists[ page_num ]['gamelist'][ i ] )
                        done = True
                        break
        self.update_cache_gamelist( cached_gamelists )
