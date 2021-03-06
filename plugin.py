#
#   Spotify Plugin
#
#   Daan Jansen, 2018
#   https://github.com/DaanJJansen/domoticz-spotify
#

"""
<plugin key="Spotify" name="Spotify Plugin" author="djj" version="0.2" wikilink="https://github.com/DaanJJansen/domoticz-spotify" externallink="https://api.spotify.com">
    <params>
        <param field="Address" label="Domoticz IP Address" width="200px" required="true" default="localhost"/>
        <param field="Port" label="Port" width="40px" required="true" default="8080"/>
        <param field="Mode1" label="Client ID" width="200px" required="true" default=""/>
        <param field="Mode2" label="Client Secret" width="200px" required="true" default=""/>
        <param field="Mode3" label="Code" width="400px" required="true" default=""/>
        <param field="Mode5" label="Poll intervall" width="100px" required="true">
            <options>
                <option label="None" value=0/>
                <option label="30 seconds" value=1/>
                <option label="5 minutes" value=10 default="true"/>
                <option label="15 minutes" value=30/>
                <option label="30 minutes" value=60/>
                <option label="60 minutes" value=120/>
            </options>
        </param>
    	<param field="Mode6" label="Debug" width="75px">
    		<options>
        		<option label="True" value="Debug"/>
        		<option label="False" value="Normal"  default="True" />
    		</options>
    	</param>
    </params>
</plugin>
"""

try:
    import Domoticz
    local = False
except ImportError:
    local = True
    import fakeDomoticz as Domoticz
    from fakeDomoticz import Devices
    from fakeDomoticz import Parameters


import urllib.request
import urllib.error
import urllib.parse
import base64
import json
import time

#DEFINES
SPOTIFYDEVICES = 1


#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class BasePlugin:
    def __init__(self):
        self.spotifyToken = {"access_token":"",
                             "refresh_token":"",
                             "retrievaldate":""
                             }
        self.spotifySearchParam = ["searchTxt"]
        self.tokenexpired = 3600
        self.spotArrDevices = {}
        self.spotifyAccountUrl = "https://accounts.spotify.com/api/token"
        self.spotifyApiUrl = "https://api.spotify.com/v1"
        self.heartbeatCounterPoll = 1
        self.blError = False
        self.blDebug = False
        

    def onStart(self):

        

        if Parameters["Mode6"] == "Debug":
            self.blDebug = True

        for var in ['Mode1','Mode2','Mode3']:
            if Parameters[var] == "":
                Domoticz.Error('No client_id, client_secret and/or code is set in hardware parameters')
                self.blError = True
                return None

        if not self.getUserVar():
            self.blError = True
            return None
            

        for key, value in self.spotifyToken.items():
            if value == '':
                Domoticz.Log("Not all spotify token variables are available, let's get it")
                if not self.spotAuthoriseCode():
                    self.blError = True
                    return None
                break

        self.checkDevices()

        Domoticz.Heartbeat(30)


    def checkDevices(self):
        Domoticz.Log("Checking if devices exis")
        
        if SPOTIFYDEVICES not in Devices:
            Domoticz.Log("Spotify devices selector does not exist, creating device")

            strSelectorNames = 'Off'
            dictOptions = self.buildDeviceSelector(strSelectorNames)
            
            Domoticz.Device(Name="devices", Unit=SPOTIFYDEVICES, Used=1, TypeName="Selector Switch", Switchtype=18, Options = dictOptions, Image=8).Create()
        else:
            self.updateDeviceSelector()

    def updateDeviceSelector(self):
        if self.blDebug:
            Domoticz.Log("Updating spotify devices selector")
        strSelectorNames = Devices[SPOTIFYDEVICES].Options['LevelNames']
        dictOptions = self.buildDeviceSelector(strSelectorNames)

        if dictOptions != Devices[SPOTIFYDEVICES].Options:
            Devices[SPOTIFYDEVICES].Update(nValue=Devices[SPOTIFYDEVICES].nValue, sValue=Devices[SPOTIFYDEVICES].sValue, Options=dictOptions)
        
            
    def buildDeviceSelector(self, strSelectorNames):

        spotDevices = self.spotDevices()
        if self.blDebug:
            Domoticz.Log('JSON Returned from spotify listed available devices: ' + str(spotDevices))
            
        strSelectorActions = ''
        

        lstSelectorNames=strSelectorNames.split("|")
        
        x=1
        while x<len(lstSelectorNames):
            strSelectorActions += '|'
            x+=1

        
        intCounter = (len(lstSelectorNames) * 10)

        for device in spotDevices['devices']:
            if device['name'] not in lstSelectorNames:
                strSelectorNames += '|' + device['name']
                strSelectorActions += '|'
                self.spotArrDevices.update({str(intCounter):device['id']})
                intCounter += 10
            else:
                self.spotArrDevices.update({str(lstSelectorNames.index(device['name'])*10):device['id']})

        if self.blDebug:
            Domoticz.Log('Local array listing selector level with deviceids: ' + str(self.spotArrDevices))
                

        dictOptions = {"LevelActions": strSelectorActions,
                       "LevelNames": strSelectorNames,
                       "LevelOffHidden": "false",
                       "SelectorStyle": "1"}

        return dictOptions
    
            

        

    def spotGetBearerHeader(self):
        tokenSecElapsed = time.time() - float(self.spotifyToken['retrievaldate'])
        if tokenSecElapsed > self.tokenexpired:
            Domoticz.Log('Token expired, getting new one using refresh_token')
            self.spotGetRefreshToken()

        return {"Authorization": "Bearer " + self.spotifyToken['access_token']}

        
        

    def spotDevices(self):
        try:
            url = self.spotifyApiUrl + '/me/player/devices'
            headers = self.spotGetBearerHeader()

            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req)

            strResponse = response.read().decode('utf-8')
            return json.loads(strResponse)
        
        except urllib.error.URLError as err:
            Domoticz.Error("Unkown error: code: %s, msg: %s" % (str(err.code), str(err.args)))
            return None
            
            
        

    def getUserVar(self):
        try:
            variables = DomoticzAPI({'type':'command','param':'getuservariables'}, self.blDebug)
        
            if variables:
                valuestring = ""
                missingVar = []
                lstDomoticzVariables = list(self.spotifyToken.keys()) + self.spotifySearchParam
                if "result" in variables:
                    for intVar in lstDomoticzVariables:
                        intVarName = Parameters["Name"] + '-' + intVar
                        try:
                            result = next((item for item in variables["result"] if item["Name"] == intVarName))
                            if intVar in self.spotifyToken:
                                self.spotifyToken[intVar] = result['Value']
                            if self.blDebug:
                                Domoticz.Log(str(result))
                        except:
                            missingVar.append(intVar)   
                else:
                    for intVar in lstDomoticzVariables:
                        missingVar.append(intVar)
                        
                if len(missingVar) > 0:
                    strMissingVar = ','.join(missingVar)
                    Domoticz.Log("User Variable {} does not exist. Creation requested".format(strMissingVar))
                    for variable in missingVar:
                        DomoticzAPI({"type":"command","param":"saveuservariable","vname":Parameters["Name"] + '-' + variable,"vtype":"2","vvalue":""}, self.blDebug)
                
                return True
            else:
                raise Exception("Cannot read the uservariable holding the persistent variables")
            
        except Exception as error:
            Domoticz.Error(str(error))

        
            

    def saveUserVar(self):
        try:
            for intVar in self.spotifyToken:
                intVarName = Parameters["Name"] + '-' + intVar
                DomoticzAPI({"type":"command","param":"updateuservariable","vname":intVarName,"vtype":"2","vvalue":str(self.spotifyToken[intVar])}, self.blDebug)
        except Exception as error:
            Domoticz.Error(str(error))

    def spotGetRefreshToken(self):
        try:
            
            url = self.spotifyAccountUrl
            headers = self.returnSpotifyBasicHeader()

            data = {'grant_type':'refresh_token',
                    'refresh_token': self.spotifyToken['refresh_token']}
            data = urllib.parse.urlencode(data)

            req = urllib.request.Request(url, data.encode('ascii'), headers)
            response = urllib.request.urlopen(req)

            strResponse= response.read().decode('utf-8')
            if self.blDebug:
                Domoticz.Log('Spotify response accestoken based on refresh: ' + str(strResponse))
                
            jsonResponse = json.loads(strResponse)

            self.saveSpotifyToken(jsonResponse)
        except:
            Domoticz.Error('Seems something with wrong with token response from spotify') 

    def returnSpotifyBasicHeader(self):

        client_id = Parameters["Mode1"] 
        client_secret = Parameters["Mode2"] 
        login = client_id + ':' + client_secret
        base64string = base64.b64encode(login.encode())
        header = {'Authorization': 'Basic ' + base64string.decode('ascii')}
        if self.blDebug:
            Domoticz.Log('For basic headers using client_id: %s, client_secret: %s' % (client_id, client_secret))

        return header
        
    
   

    def spotAuthoriseCode(self):
        try:
            code = Parameters["Mode3"]
            url = self.spotifyAccountUrl
            data = {'grant_type':'authorization_code',
                    'code':code,
                    'redirect_uri':'http://localhost'}
            if self.blDebug:
                Domoticz.Log('Getting tokens using data: %s' % (data))
            data = urllib.parse.urlencode(data)
            
            headers = self.returnSpotifyBasicHeader()
            if self.blDebug:
                Domoticz.Log('Getting tokens using header: %s' % (headers))

            try:
                req = urllib.request.Request(url, data.encode('ascii'), headers)
                response = urllib.request.urlopen(req)

                strResponse= response.read().decode('utf-8')
                if self.blDebug:
                    Domoticz.Log('Spotify tokens based on authorisation code: ' + str(strResponse))
                jsonResponse = json.loads(strResponse)
                    

                self.saveSpotifyToken(jsonResponse)

                return True
            
            except urllib.error.HTTPError as err:
                errmsg = "Error occured in request for getting acces_tokens from Spotify, error code: %s, reason: %s." %(err.code,err.reason)
                if err.code == 400:
                    errmsg += " Seems either client_id, client_secret or code is incorrect. Please note that the code received from Spotify could only be used once. Please get a new one from spotify."
                Domoticz.Error(errmsg)
            
        except Exception as error:
            Domoticz.Error(error)

            
            
    def saveSpotifyToken(self, response):
        try:
            for intVar in self.spotifyToken:
                if intVar in response:
                    self.spotifyToken[intVar] = response[intVar]
            self.spotifyToken['retrievaldate'] = time.time()
            Domoticz.Log('Succesfully got spotify tokens, saving data in user domoticz user variables')
            self.saveUserVar()
        except:
            Domoticz.Error('Seems something with wrong with token response from spotify')

    def spotSearch(self, input, type):

        
        url = self.spotifyApiUrl + "/search?q=%s&type=%s&market=NL&limit=10" % (urllib.parse.quote(input), type)
        if self.blDebug:
            Domoticz.Log('Spotify search url: ' + str(url))
            
        headers = self.spotGetBearerHeader()

        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req)

        jsonResponse = json.loads(response.read().decode('utf-8'))
        foundItems = jsonResponse['%ss' % type]['items']

        if self.blDebug:
            Domoticz.Log('First result of spotify search: ' + str(foundItems[0]))
            
        rsltString = 'Found ' + type + ' ' + foundItems[0]['name']
        if type == 'track':
            tracks = []
            for track in foundItems:
                tracks.append(track['uri'])
            returnData = {"uris": tracks}
        else:
            returnData = {"context_uri": foundItems[0]['uri']}

        if type  == 'album' or type == 'track':
            rsltString += ' by ' + foundItems[0]['artists'][0]['name']
            
        Domoticz.Log(rsltString) 
        return returnData

    def spotPause(self):
        try:

            url = self.spotifyApiUrl + "/me/player/pause"
            headers = self.spotGetBearerHeader()

            req = urllib.request.Request(url, headers=headers, method='PUT')
            response = urllib.request.urlopen(req)
            Domoticz.Log("Succesfully paused track")

        except urllib.error.HTTPError as err:
            if err.code == 403:
                Domoticz.Error("User non premium")
            elif err.code == 400:
                Domoticz.Error("Device id not found")
            else:
                Domoticz.Error("Unkown error, msg: " + str(err.msg))

    def spotCurrent(self):
        try:

            url = self.spotifyApiUrl + "/me/player"
            headers = self.spotGetBearerHeader()

            req = urllib.request.Request(url, headers=headers, method='GET')
            response = urllib.request.urlopen(req)
            

            if self.blDebug == True:
                Domoticz.Log("Succesfully retrieved current playing state")
                Domoticz.Log('Retrieved current playing state having code %s' % (response.code))


            return response

        except urllib.error.HTTPError as err:
            Domoticz.Error("Unkown error %s, msg: %s" % (err.code, err.msg))
    
    def spotPlay(self, input, deviceLvl):

        try:

            if deviceLvl not in self.spotArrDevices:
                self.updateDeviceSelector()
                if deviceLvl not in self.spotArrDevices:
                    raise urllib.error.HTTPError(url='',msg='',hdrs='', fp='', code=404)
            
            device = self.spotArrDevices[deviceLvl]
            url = self.spotifyApiUrl + "/me/player/play?device_id=" + device  
            headers = self.spotGetBearerHeader()

            data = json.dumps(input).encode('utf8')


            req = urllib.request.Request(url, headers=headers, data=data, method='PUT')
            response = urllib.request.urlopen(req)
            self.updateDomoticzDevice(SPOTIFYDEVICES, 1, str(deviceLvl))
            Domoticz.Log("Succesfully started playback")

        except urllib.error.HTTPError as err:
            if err.code == 403:
                Domoticz.Error("Error playback, you need to be premium member")
            elif err.code == 400:
                Domoticz.Error("Error playback, right scope requested?")
            elif err.code == 404:
                Domoticz.Error("Device not found, went offline?")
            else:
                Domoticz.Error("Unkown error, msg: " + str(err.msg))
        

    def onHeartbeat(self):
        if not self.blError:
            if Parameters["Mode5"] != "0" and self.heartbeatCounterPoll == int(Parameters["Mode5"]):
                if self.blDebug:
                    Domoticz.Log('Polling')
                response = self.spotCurrent()
                if response.code == 204 and Devices[SPOTIFYDEVICES].sValue != '0':
                    self.updateDomoticzDevice(SPOTIFYDEVICES, 0, "0")
                elif response.code == 200:
                    resultJson = json.loads(response.read().decode('utf-8'))

                    try:
                        if resultJson['is_playing'] == False:
                            self.updateDomoticzDevice(SPOTIFYDEVICES, 0, "0")
                        else:
                            lstSelectorLevel = catchDeviceSelectorLvl(resultJson['device']['name'])
                            self.updateDomoticzDevice(SPOTIFYDEVICES, 1, lstSelectorLevel)
                                
                    except ValueError:
                        try:
                            if self.blDebug:
                                Domoticz.Log('Playing on device %s which was unkown, trying to update domoticz device to correctly update playback information.' % (str(resultJson['device']['name'])))
                            self.updateDeviceSelector()
                            lstSelectorLevel = catchDeviceSelectorLvl(resultJson['device']['name'])
                            self.updateDomoticzDevice(SPOTIFYDEVICES, 1, lstSelectorLevel)
                        except ValueError:
                            Domoticz.Error("Current playing device not found by domoticz, cant update")
                        

                    except UnicodeEncodeError:
                        #jsonresult is empty, meaning nothing is playing
                        self.updateDomoticzDevice(SPOTIFYDEVICES, 0, "0")
                        
                    
                self.heartbeatCounterPoll = 1
            else:
                self.heartbeatCounterPoll += 1
            
            return True

    def updateDomoticzDevice(self, idx, nValue, sValue):
        if Devices[idx].sValue != sValue or Devices[idx].nValue != nValue:
            if self.blDebug == True:
                Domoticz.Log('Update for device %s with nValue: %s and sValue %s' % (idx, nValue, sValue))
            Devices[idx].Update(nValue, sValue)

            

    def onCommand(self, Unit, Command, Level, Hue):
        if (self.blDebug ==  True):
            Domoticz.Log("Spotify: onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
            Domoticz.Log("nValue=%s, sValue=%s" % (str(Devices[SPOTIFYDEVICES].nValue), str(Devices[SPOTIFYDEVICES].sValue)))

        if Unit == SPOTIFYDEVICES:
            try:
                variables = DomoticzAPI({'type':'command','param':'getuservariables'}, self.blDebug)
            except Exception as error:
                Domoticz.Error(error)

            if Level == 0:
                #Spotify turned off
                self.updateDomoticzDevice(Unit, 0, str(Level))
                self.spotPause()
                
            else:
                searchVariable = next((item for item in variables["result"] if item["Name"] == Parameters["Name"] + '-searchTxt'))
                searchString = searchVariable['Value']
                Domoticz.Log('Looking for ' + searchString)
                searchResult = None

                if searchString != "":
                    for type in ['artist','track','playlist','album']:
                        if type in searchString:
                            strippedSearch = searchString.replace(type,'').lstrip()
                            if self.blDebug:
                                Domoticz.Log('Search type: ' + type)
                                Domoticz.Log('Search string: ' + strippedSearch)
                            searchResult = self.spotSearch(strippedSearch,type)
                            break

                if not searchResult:
                    Domoticz.Error("No correct type found in search string, use either artist, track, playlist or album")
                else:
                    self.spotPlay(searchResult,str(Level))

            

_plugin = BasePlugin()

def onStart():
    _plugin.onStart()

def onHeartbeat():
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)


#############################################################################
#                         Domoticz helper functions                         #
#############################################################################

def catchDeviceSelectorLvl(name):
    lstSelectorNames = Devices[SPOTIFYDEVICES].Options['LevelNames'].split('|')
    lstSelectorLevel = str(lstSelectorNames.index(name)*10)
    return lstSelectorLevel
    

def DomoticzAPI(APICall, blDebug):
    resultJson = None
    url = "http://{}:{}/json.htm?{}".format(Parameters["Address"], Parameters["Port"], urllib.parse.urlencode(APICall, safe="&="))
    if blDebug:
        Domoticz.Log("Calling domoticz API: {}".format(url))
    try:
        req = urllib.request.Request(url)
        if Parameters["Username"] != "":
            Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
            credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
            encoded_credentials = base64.b64encode(credentials.encode('ascii'))
            req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

        response = urllib.request.urlopen(req)

        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["status"] != "OK":
                raise Exception("Domoticz API returned an error: status = {}".format(resultJson["status"]))
        else:
            raise Exception("Domoticz API: http error = {}".format(response.status))
    except:
        raise Exception("Error calling '{}'".format(url))
    
    return resultJson






#############################################################################
#                       Local test helpers                                  #
#############################################################################

if local:
    onStart()

    #onHeartbeat()

    #onCommand(1,'Off',0,'')
    onCommand(1,'Set level',20,'')

    
    

