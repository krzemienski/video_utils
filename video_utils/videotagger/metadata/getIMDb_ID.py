import logging;
import os, re;
from imdb import IMDb;

TVDb = None;                                                                    # Set tvdb to None
try:
  from video_utils.api_keys import tvdb as tvdb_key;                            # Attempt to import the API key from the api_keys module
except:
  tvdb_key = os.environ.get('TVDB_API_KEY', None);                              # On exception, try to get the API key from the TVDB_API_KEY environment variable

if tvdb_key:                                                                    # If the tvdb_key variable is valid
  import tvdbsimple as TVDb;                                                    # Import tvdbsimple as tvdb; this will make if tvdb: return True
  TVDb.KEYS.API_KEY = tvdb_key;                                                 # Set the API_KEY for the tvdbsimple
else:                                                                           # Else, get a logger and log an error
  logging.getLogger(__name__).error( 
    "API key for TVDb could NOT be imported!"
  );

imdbFMT = 'tt{}';                                                               # Format string for IMDb id
yearPat = re.compile( r'\(([0-9]{4})\)' );                                      # Pattern for finding year in series name

def getIMDb_ID( series_name, episode_title, season_ep = None ):
  '''
  Name:
    getIMDb_ID
  Purpose:
    A function that attempts to get the IMDb ID (i.e., tt0000000) based
    on the information from an input file path.

    This is designed to be used for Plex DVR TV Episode files, which
    have the file naming convention of:
      Series Name - S00E00 - Episode title.ts
  Inputs:
    in_file  : Full path to file to get IMDb ID for
  Outputs:
    Returns the IMDb ID if found, or None if not found.
  '''
  log = logging.getLogger(__name__);                                            # Initialize logger

  log.debug('Extracting information from file name');
  
  year = yearPat.findall( series_name );                                        # Try to find a year in the series name
  if len(year) == 1:                                                            # If found a year
    year   = int(year[0]);                                                      # Get year from list
    series_name = yearPat.sub('', series_name);                                 # Replace year in the series name with nothing
  else:                                                                         # Else
    year   = None;                                                              # Set year equal to None
  series_name = series_name.strip();                                            # Remove leading/trailing spaces
  log.debug(
    'Series: {}, Year: {}, Ep #: {}, Title: {}'.format(
      series_name, year, se, episode_title)
  )

  ###############
  ### IMDb serach
  log.info( 'Attempting to get IMDb ID from IMDb' );               
  imdb = IMDb();                                                                # Initialize IMDb instance
  res  = imdb.search_episode( episode_title );                                  # Search for the episode title on IMDb
  log.debug( 'IMDb search returned {} matches'.format( len(res) ) );            # Debugging information
  for r in res:                                                                 # Iterate over all the results from IMDb
    if r['episode of'].lower() in series_name.lower():                          # If the series name from IMDb is in the series name from the file
      log.debug('Found series with matching name');
      if 'series year' in r and year:                                           # If the 'series year' key is in the result AND the local year is defined
        log.debug('Series has year information');
        if r['series year'] != year: 
          log.debug('Series year did NOT match');
          continue;                                                             # If the result series year NOT match the local series year, skip series
      log.info( 'IMDb ID found from IMDb search')
      return imdbFMT.format( r.getID() );                                       # Return the IMDb id
  log.warning( 'IMDb search failed' )
  
  ###############
  ### TVDb serach
  if not TVDb: return None;                                                     # If the TVDb was NOT loaded, just return None;
  log.info( 'Attempting to get IMDb ID from TVDb' );               

  tvdb = TVDb.Search();                                                         # Initialize search for TVDb
  try:                                                                          # Try to
    res  = tvdb.series_name( series_name );                                     # Search for the series on the TVDb
  except:                                                                       # On exception
    pass;                                                                       # Do nothing
  else:                                                                         # If try was success
    log.debug( 'TVDb series search returned {} matches'.format( len(res) ) );   # Debugging information
    for r in res:                                                               # Iterate over all search results
      if str(year) in r['firstAired']:                                          # If the local year is in the firstAird tag
        log.debug( 'Found series with same firstAired year' );                  # Debugging information
        eps = TVDb.Series( r['id'] ).Episodes.all();                            # Get list of all episodes in series
        log.debug( 'TVDb returned {} episodes in the series'.format(len(eps)) );# Debugging information
        for ep in eps:                                                          # Iterate over all episodes
          if (ep['episodeName'].lower() in episode_title.lower()):              # If the episode name is in the local title and there is an imdbId in the ep
            log.debug( 'Found episode with same name' );
            if ('imdbId' in ep) and (ep['imdbId'] != ''):                       # If imdbId key exists AND imdbId value is NOT empty
              log.info( 'IMDb ID found from TVDb search' )
              return ep['imdbId'];                                              # Return it
  log.warning( 'TVDb search failed' );
  return None;