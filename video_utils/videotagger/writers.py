import logging
import os, sys, re
from mutagen import mp4
from xml.etree import ElementTree as ET
from subprocess import Popen, STDOUT, DEVNULL

from ..utils.checkCLI import checkCLI
from .utils import downloadCover

try:
  MKVPROPEDIT = checkCLI( 'mkvpropedit' )
except:
  logging.getLogger(__name__).error('mkvpropedit NOT installed')
  MKVPROPEDIT = None

freeform = lambda x: '----:com.apple.iTunes:{}'.format( x )                             # Functio

TVDB_ATTRIBUTION = 'TV and/or Movie information and images are provided by TheTVDB.com, but we are not endorsed or certified by TheTVDB.com or its affiliates. See website at https://thetvdb.com/.'
TMDB_ATTRIBUTION = 'TV and/or Movie information and images are provided by themoviedb.com (TMDb), but we are not endorsed or certified by TMDb or its affiliates. See website at https://themoviedb.org/.'

def encoder( val ):
  if isinstance(val, (tuple, list,)):
    return [i.encode() for i in val]
  elif isinstance( val, str ):
    return val.encode()
  else:
    return val

# A dictionary where keys are the starndard internal tags and values are MP4 tags
# If a value is a tuple, then the first element is the tag and the seoncd is the
# encoder function required to get the value to the correct format
MP4KEYS = {
  'year'       :  '\xa9day',
  'title'      :  '\xa9nam',
  'seriesName' :  'tvsh',
  'seasonNum'  : ('tvsn', lambda x: [x]),
  'episodeNum' : ('tves', lambda x: [x]),
  'genre'      :  '\xa9gen',
  'kind'       : ('stik', lambda x: [9] if x == 'movie' else [10]),
  'sPlot'      :  'desc',
  'lPlot'      : (freeform('LongDescription'),   encoder,),
  'rating'     : (freeform('ContentRating'),     encoder,),
  'prod'       : (freeform('Production Studio'), encoder,),
  'cast'       : (freeform('Actor'),             encoder,),
  'dir'        : (freeform('Director'),          encoder,),
  'wri'        : (freeform('Writer'),            encoder,),
  'comment'    : '\xa9cmt',
  'cover'      :  'covr'
}

# A dictionary where keys are the standard internal tags and values are MKV tags
# THe first value of each tuple is the level of the tag and the second is the tag name
# See: https://matroska.org/technical/specs/tagging/index.html
MKVKEYS = {
  'year'       : (50, 'DATE_RELEASED'),
  'title'      : (50, 'TITLE'),
  'seriesName' : (70, 'TITLE'),
  'seasonNum'  : (60, 'PART_NUMBER'),
  'episodeNum' : (50, 'PART_NUMBER'),
  'genre'      : (50, 'GENRE'),
  'kind'       : (50, 'CONTENT_TYPE'),
  'sPlot'      : (50, 'SUMMARY'),
  'lPlot'      : (50, 'SYNOPSIS'),
  'rating'     : (50, 'LAW_RATING'),
  'prod'       : (50, 'PRODUCION_STUDIO'),
  'cast'       : (50, 'ACTOR'),
  'dir'        : (50, 'DIRECTOR'),
  'wri'        : (50, 'WRITTEN_BY'),
  'comment'    : (50, 'COMMENT'),
  'cover'      : 'covr'
}

########################################################################
def toMP4( metaData ):
  '''
  Purpose:
    Function to convert internal tags to MP4 tags
  Inputs:
    metadata : Dictionary containing metadata returned by a TVDb or TMDb
                 movie or episde object
  Keywords:
    None.
  Returns:
    Returns dictionary with valid MP4 tags as keys and correctly
    encoded values
  '''
  keys = list( metaData.keys() )                                                        # Get list of all keys currently in dictioanry
  for key in keys:                                                                      # Iterate over all keys
    val     = metaData.pop( key )                                                       # Get value in key; poped off so no longer exists in dict
    keyFunc = MP4KEYS.get( key, None )                                                  # Get keyFunc value from MP4KEYS; default to None
    if keyFunc:                                                                         # If not None
      if isinstance( keyFunc, tuple ):                                                  # If keyFunc is a tuple
        key = keyFunc[0]                                                                # Get new key
        val = keyFunc[1]( val )                                                         # Encode values
      else:                                                                             # Else
        key = keyFunc                                                                   # Get new key
      metaData[key] = val                                                               # Write encoded data under new key back into metadata
  return metaData                                                                       # Return metadata

def toMKV( metaData ):
  '''
  Purpose:
    Function to convert internal tags to MKV tags
  Inputs:
    metadata : Dictionary containing metadata returned by a TVDb or TMDb
                 movie or episde object
  Keywords:
    None.
  Returns:
    Returns dictionary with valid MKV tag level and tags as keys
  '''
  keys = list( metaData.keys() )                                                        # Get list of keys currently in dictionary
  for key in keys:                                                                      # Iterate over keys
    val = metaData.pop(key)                                                             # Get value in key; popped off so no longer exists in dict
    if key in MKVKEYS:                                                                  # If key exists in MKVKEYS
      metaData[ MKVKEYS[key] ] = val                                                    # Write data udner new key back into metadata
  return metaData                                                                       # Return metadata

################################################################################
def mp4Tagger( file, metaData ):
  '''
  Name:
    mp4Tags
  Purpose:
    A function to parse information from the IMDbPY API and
    write Tag data to MP4 files.
  Inputs:
    file     : Full path of file to write metadata to.
    metaData : Dictionary of meta data where keys are internal
                  metadata keys and values are metadata values
  Outputs:
    Returns following values based on completion.
       0 : Completed successfully.
       1 : Input was NOT and MP4
       2 : IMDb ID was not valid
       3 : Failed to download information from IMDb AND themoviedb.org
       4 : Writing tags is NOT possible
       5 :  Failed when trying to remove tags from file.
       6 : Failed when trying to write tags to file.
      10 : IMDbPY not installed AND getTMDb_Info failed to import
      11 : File is too large
  Keywords:
    None
  Dependencies:
    mutagen
  Author and History: 
    Kyle R. Wodzicki     Created 18 Feb. 2018
  '''
  log = logging.getLogger(__name__)                                                     # Set up a logger
  log.debug( 'Testing file is MP4' )                                                    # Debugging information
  if not file.endswith('.mp4'):                                                         # If the input file does NOT end in '.mp4'
    log.error('Input file is NOT an MP4!!!')
    return 1                                                                            # Print message and return code one (1)

  log.debug( 'Testing file too large' )                                                 # Debugging information
  if os.stat(file).st_size > sys.maxsize:                                               # If the file size is larger than the supported maximum size
    log.error('Input file is too large!')
    return 11                                                                           # Print message and return code eleven (11)
  
  version = metaData.pop('version', '')
  comment = metaData.get('comment',   '')
  comment = ' '.join( [comment, TVDB_ATTRIBUTION, TMDB_ATTRIBUTION] ).strip()

  metaData.update( {'comment' : comment } )
  metaData  = toMP4(metaData)
  if len(metaData) == 0:
    log.warning('No metadata, cannot write tags')
    return 3

  filedir, filebase = os.path.dirname( file ), os.path.basename( file )                 # Get the directory and baseanem of the file

  log.debug('Loading file using mutagen.mp4.MP4')                                       # Debugging information
  handle = mp4.MP4(file)                                                                # Initialize mutagen MP4 handler
  log.debug('Attempting to add tag block to file')                                      # Debugging information
  try:                                                                                  # Try to...
    handle.add_tags()                                                                   # Add new tags to the file
  except mp4.error as e:                                                                # On exception, catch the error
    if 'already exists' in e.__str__():                                                 # If the error is that the tag block already exists
      log.debug('MP4 tags already exist in file.')                                      # Debugging information
      pass                                                                              # Pass
    else:                                                                               # Else, adding is not possible
      log.error('Could NOT add tags to file!')                                          # Log an error
      return 4                                                                          # Return code 4
  try:                                                                                  # Try to...
    handle.delete();                                                                    # Remove all old tags.
  except mp4.error as e:                                                                # On exception, catch the error
    log.error( e.__str__() );                                                           # Log the error
    return 5;                                                                           # Return code 5
  log.debug('Setting basic inforamtion')                                                # Debugging information
  for key, val in metaData.items():
    if key == 'covr' and val != '':
      log.debug('Attempting to get coverart')                                           # Debugging information
      fmt  = mp4.AtomDataType.PNG if val.endswith('png') else mp4.AtomDataType.JPEG     # Set format for the image
      data = downloadCover( val, text = version )
      if data is not None:
        val = [ mp4.MP4Cover( data, fmt ) ]                                             # Add image to file
      else:
        continue
    try:
      handle[key] = val
    except:
      log.warning( 'Failed to write metadata for: {}'.format(key) )

  log.debug('Saving tags to file')                                                      # Debugging information
  try:                                                                                  # Try to...
    handle.save();                                                                      # Save the tags
  except:                                                                               # On exception
    log.error('Failed to save tags to file!');                                          # Log an error
    return 6
  return 0

################################################################################
def deleteAttachments( file, n = 10 ):
  '''
  Purpose:
    Function to delete a bunch of attachments in an MKV file
  Inputs:
    file : Full path to file
  Keywords:
    n    : int, number of attachments to try to delete
  Returns:
    None.
  '''
  if not MKVPROPEDIT: return

  cmd  = [MKVPROPEDIT, file]
  for i in range(n):
    cmd += ['--delete-attachment', str(i)] 
  proc = Popen( cmd, stdout=DEVNULL, stderr=STDOUT )
  proc.wait()

################################################################################
def addTarget( ele, level ):
  '''
  Purpose:
    Add a target level to the XML file from MKV tagging
  Inputs:
    ele   : Element to add tag to
    level : Level of the tag
  Keywords:
    None.
  Returns:
    An ElementTree SbuElement instance
  '''
  tags = ET.SubElement(ele, 'Tag')                                                      # Create subelement named Tag
  targ = ET.SubElement(tags, 'Targets')                                                 # Add subelement named Targets to Tag element
  ET.SubElement(targ, 'TargetTypeValue').text = str(level)                              # Set the TargetTypeValue text
  return tags                                                                           # Return tags subelement

################################################################################
def addTag( ele, key, val ):
  '''
  Purpose:
    Add a tag to XML element for MKV tagging 
  Inputs:
    ele   : Element to add tag to
    key   : Tag name to add
    val   : Value of the tag
  Keywords:
    None.
  Returns:
    None
  '''
  if isinstance(val, (list,tuple,)):                                                    # If val is an iterable type
    val = ','.join(map(str, val))                                                       # Convert all values to string using map() and join on comma
  elif not isinstance(val, str):                                                        # Else, if not a str instance
    val = str(val)                                                                      # Convert to string

  simple = ET.SubElement(ele, 'Simple')                                                 # Add a new subelement to ele
  ET.SubElement(simple, 'Name').text   = key                                            # Set element Name to key
  ET.SubElement(simple, 'String').text = val                                            # Set element string to val

################################################################################
def mkvTagger( file, metaData ):
  '''
  Name:
    mkvTagger
  Purpose:
    A function to parse information from the IMDbPY API and
    write Tag data to MP4 files.
  Inputs:
    file     : Full path of file to write metadata to.
    metaData : Dictionary of meta data where keys are internal
                metadata keys and values are metadata values
  Outputs:
    Returns following values based on completion.
         0 : Completed successfully.
         1 : Input was NOT and MKV
         2 : IMDb ID was not valid
         3 : Failed to download information from IMDb AND themoviedb.org
         4 : Writing tags is NOT possible
         5 :    Failed when trying to remove tags from file.
         6 : Failed when trying to write tags to file.
        10 : IMDbPY not installed AND getTMDb_Info failed to import
        11 : File is too large
  Keywords:
    None.
  Dependencies:
    mkvpropedit
  Author and History: 
    Kyle R. Wodzicki     Created 18 Feb. 2018
  '''
  log = logging.getLogger(__name__);                                              # Set up a logger
  if not MKVPROPEDIT:
    log.warning( 'mkvpropedit not installed' )
    return 4

  log.debug( 'Testing file is MKV' );                                             # Debugging information
  if not file.endswith('.mkv'):                                                   # If the input file does NOT end in '.mp4'
    log.error('Input file is NOT an MKV!!!'); return 1;                         # Print message and return code one (1)

  log.debug( 'Testing file too large' );                                          # Debugging information
  if os.stat(file).st_size > sys.maxsize:                                         # If the file size is larger than the supported maximum size
    log.error('Input file is too large!'); return 11;                           # Print message and return code eleven (11)
      
  version = metaData.pop('version', '')
  comment = metaData.get('comment', '')
  comment = ' '.join( [comment, TVDB_ATTRIBUTION, TMDB_ATTRIBUTION] ).strip()           # Join all comments on space and remove leading/trailing spaces

  metaData.update( {'comment' : comment } )
  metaData  = toMKV( metaData )

  if len(metaData) == 0:
    log.warning('No metadata, cannot write tags')
    return 3

  fileDir, fileBase = os.path.split( file )                                             # Get the directory and baseanem of the file
  xmlFile           = os.path.join( fileDir, 'tags.xml' )                               # Set xml file path

  log.debug('Setting basic inforamtion');                                               # Debugging information
  top  = ET.Element('Tags')                                                             # Top-level of XML tree
  tags = {}                                                                             # Dictionary for storing XML elements

  coverFile = None
  for key, val in metaData.items():                                                     # Iterate over all key/value pairs in metadata dictionary
    if key == 'covr':                                                                   # If key is covr
      coverFile = downloadCover( val, saveDir = fileDir, text = version )               # Download cover
    else:                                                                               # Else
      TargetTypeValue, tag = key                                                        # Get TargetTypeValue and tag from the key tuple
      if TargetTypeValue not in tags:                                                   # If the TargetTypeValue is not in tags
        tags[TargetTypeValue] = addTarget( top, TargetTypeValue )                       # Add it using the addTarget function
      addTag( tags[TargetTypeValue], tag, val )                                         # Add the tag/value to the target

  ET.ElementTree(top).write( xmlFile )                                                  # Write xml data to file

  cmd = [MKVPROPEDIT, file, '-t', 'all:{}'.format(xmlFile)]                             # Set base command for adding tags

  if coverFile and os.path.isfile( coverFile ):                                         # If the 'full-size cover url' is in the metaData
    deleteAttachments( file )                                                           # Delete any existing attachments
    cmd += ['--attachment-name', 'Poster']                                              # Set attachment name to Poster
    cmd += ['--add-attachment',  coverFile]                                             # Add covert art file

  log.debug('Saving tags to file');                                                     # Debugging information

  proc = Popen(cmd, stdout = DEVNULL, stderr = STDOUT)                                  # Actually tag file
  proc.wait()                                                                           # Wait for tagging to finish
  
  try:
    os.remove( xmlFile )
  except:
    pass

  try:
    os.remove( coverFile )
  except:
    pass
  
  if (proc.returncode != 0): 
    log.error('Failed to save tags to file!');                                  # Log an error
    return 6
 
  return 0
