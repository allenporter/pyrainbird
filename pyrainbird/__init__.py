import json
import math
import http.client
import time
import logging

from Crypto.Hash import SHA256
from Crypto.Cipher import AES
from Crypto import Random


class RainbirdController:
    # COMMAND FILE RAINBIRD API
    jsoncommands="""{
        "ControllerCommands" :
        {
            "ModelAndVersionRequest" : {"command" : "02", "response": "82",  "length": 1},
            "AvailableStationsRequest" : {"command" : "03", "parameter" : 0, "response": "83", "length" : 2},
            "CommandSupportRequest" : {"command" : "04", "commandToTest" : "02", "response" : "84", "length" : 2},
            "SerialNumberRequest" : {"command" : "05", "response" : "85", "length" : 1},
            "CurrentTimeRequest" : {"command" : "10", "response" : "90", "length" : 1},
            "CurrentDateRequest" : {"command" : "12", "response" : "92", "length" : 1},
            "WaterBudgetRequest" : {"command" : "30", "parameter" : 0, "response" : "B0", "length" : 2},
            "CurrentRainSensorStateRequest" : {"command" : "3E", "response" : "BE", "length" : 1},
            "CurrentStationsActiveRequest" : {"command" : "3F", "parameter" : 0, "response" : "BF", "length" : 2},
            "ManuallyRunProgramRequest" : {"command" : "38", "parameter" : 0, "response" : "01", "length" : 2},
            "ManuallyRunStationRequest" : {"command" : "39", "parameterOne" : 0, "parameterTwo" : 0, "response" : "01", "length" : 4},
            "TestStationsRequest" : {"command" : "3A", "parameter" : 0, "response" : "01", "length" : 2},
            "StopIrrigationRequest" : {"command" : "40", "response" : "01",  "length": 1},
            "RainDelayGetRequest" : {"command" : "36", "response" : "B6", "length" : 1},
            "RainDelaySetRequest" : {"command" : "37", "parameter" : 0, "response" : "01", "length" : 3},
            "AdvanceStationRequest" : {"command" : "42", "parameter" : 0, "response" : "01", "length" : 2},
            "CurrentIrrigationStateRequest" : {"command" : "48", "response": "C8", "length": 1},
            "CurrentScheduleRequest" : { "command" : "20", "parameterOne" : 0, "parameterTwo" : 0 ,"response" : "A0", "length": 3 }
        },
        "ControllerResponses" :
        {
            "00" : {"length" : 3, "type": "NotAcknowledgeResponse", "commandEcho": {"position" : 2, "length" : 2}, "NAKCode" : {"position" : 4, "length" : 2} },
            "01" : {"length" : 2, "type": "AcknowledgeResponse", "commandEcho": {"position" : 2, "length" : 2} },
            "82" : {"length" : 5, "type": "ModelAndVersionResponse", "modelID": {"position" : 2, "length" : 4},"protocolRevisionMajor": {"position" : 6, "length" : 2},"protocolRevisionMinor": {"position" : 8, "length" : 2}},
            "83" : {"length" : 6, "type" : "AvailableStationsResponse", "pageNumber" : {"position" : 2, "length" : 2}, "setStations" : {"position" : 4, "length" : 8}},
            "84" : {"length" : 3,"type" : "CommandSupportResponse", "commandEcho" : {"position" : 2, "length" : 2}, "support" : {"position" : 4, "length" : 2}},
            "85" : {"length" : 9, "type" : "SerialNumberResponse", "serialNumber" : {"position" : 2, "length" : 16}},
            "90" : {"length" : 4, "type" : "CurrentTimeResponse", "hour" : {"position" : 2, "length" : 2}, "minute" : {"position" : 4, "length" : 2}, "second" : {"position" : 6, "length" : 2}},
            "92" : {"length" : 4, "type" : "CurrentDateResponse", "day" : {"position" : 2, "length" : 2}, "month" : {"position" : 4, "length" : 1}, "year" : {"position" : 5, "length" : 3}},
            "B0" : {"length" : 4, "type" : "WaterBudgetResponse", "programCode" : {"position" : 2, "length": 2}, "highByte" : {"position" : 4, "length" : 2}, "lowByte" : {"position" : 6, "length" : 2}},
            "BE" : {"length" : 2, "type" : "CurrentRainSensorStateResponse", "sensorState" : {"position" : 2, "length" : 2}},
            "BF" : {"length" : 6, "type" : "CurrentStationsActiveResponse", "pageNumber" : {"position" : 2, "length" : 2}, "activeStations" : {"position" : 4, "length" : 8}},
            "B6" : {"length" : 3, "type" : "RainDelaySettingResponse", "delaySetting" : {"position" : 2, "length" : 4}},
            "C8" : {"length" : 2, "type" : "CurrentIrrigationStateResponse", "irrigationState" : {"position" : 2, "length" : 2}}
        }
    }"""

    
    def __init__ (self, logger = logging.getLogger(__name__)):
        # Load JSON with commands
        self.rainbirdCommands = json.loads(self.jsoncommands)
        self.rainbirdEncryption = self.RainbirdEncryption()
        self.rainbirdPassword = None
        self.rainbirdserver = None
        self.logger = logger

    def stopIrrigation(self):
        self.logger.debug("Irrigation stop requested")
        resp=self.request("StopIrrigation")
        if (resp != ""):
          jsonresult=json.loads(resp)
          if (jsonresult["result"]["data"][:2] == "01"):
           self.logger.debug("Irrigation stop request acknowledged")
           return 1
          else:
            self.logger.warning("Irrigation stop request NOT acknowledged")
            return -1
        self.logger.warning("Request resulted in no response")
        return 0
        
    def startIrrigation(self,zone,minutes):
            self.logger.debug("Irrigation start requested for zone "+str(zone)+" for duration " + str(minutes))
            resp=self.request("ManuallyRunStation",zone,minutes)
            if (resp != ""):
                jsonresult=json.loads(resp)
                if (jsonresult["result"]["data"][:2] == "01"):
                    self.logger.debug("Irrigation request acknowledged")
                    return 1
                else:
                    self.logger.warning("Irrigation request NOT acknowledged")
                    return -1
            self.logger.warning("Request resulted in no response")
            return 0

    def currentIrrigation(self):
            self.logger.debug("Requesting current Irrigation station")
            resp=self.request("CurrentStationsActive")
            if (resp != ""):
                jsonresult=json.loads(resp)
                if (jsonresult["result"]["data"][:2] == "BF"):
                    val=jsonresult["result"]["data"][4:8]
                    if (int(val[:2]) != 0):
                      self.logger.debug("Status request acknowledged")
                      return round(math.log(int(val[:2]),2)+1)
                    else:
                      return 0
                else:
                   self.logger.warning("Status request NOT acknowledged")
                   return -1
            else:
               self.logger.warning("Request resulted in no response")
               return -1

    def currentRainSensorState(self):
            self.logger.debug("Requesting current Rain Sensor State")
            resp=self.request("CurrentRainSensorState")
            if (resp != ""):
                jsonresult=json.loads(resp)
                if (jsonresult["result"]["data"][:2] == "BE"):
                    val=jsonresult["result"]["data"][3:4]
                    self.logger.debug("Current rainsensor state: "+str(val))
                    return str(val)
                else:
                   self.logger.warning("Status request failed with wrong respone")
                   return -1
            else:
               self.logger.warning("Request resulted in no response")
               return -1

    def setConfig(self,server,password,retry=3,retry_sleep=10):
        self.rainbirdPassword = password
        self.rainbirdServer = server
        self.retry=retry
        self.retry_sleep=retry_sleep

    def send_rainbird_command (self,rbdata):
            senddata = self.rainbirdEncryption.encrypt(rbdata ,self.rainbirdPassword)
            head = {
            "Accept-Language": "en",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "RainBird/2.0 CFNetwork/811.5.4 Darwin/16.7.0",
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Connection": "keep-alive",
            "Content-Type": "application/octet-stream"}

            resp = None
            
            for x in range(0,self.retry):
                try:
                    h = http.client.HTTPConnection(self.rainbirdServer,80,timeout=20)
                    h.request("POST","/stick",senddata,head)
                    resp = h.getresponse()
                except:
                    pass
                if (resp is None or resp.status != 200):
                    time.sleep(self.retry_sleep)
                    h.close()
                else:
                    resultdata=resp.read()
                    decrypteddata=(self.rainbirdEncryption.decrypt(resultdata,self.rainbirdPassword)).decode("UTF-8")
                    self.logger.debug("Response from line: " + str(decrypteddata))
                    return decrypteddata
                    break
            return ""
            h.close()

    def request (self,command, cmd_param1=0, cmd_param2=0):
            cmd_code=self.rainbirdCommands["ControllerCommands"][command+"Request"]["command"]
            cmd_len=self.rainbirdCommands["ControllerCommands"][command+"Request"]["length"]
            if ("parameter" in self.rainbirdCommands["ControllerCommands"][command+"Request"]):
                request = '{"id":9,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"'+cmd_code+'{0:02x}'.format(cmd_param1)+'","length":'+str(cmd_len)+'}}'
            elif ("parameterOne" in self.rainbirdCommands["ControllerCommands"][command+"Request"]):
                request = '{"id":9,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"'+cmd_code+"00"+'{0:02x}'.format(cmd_param1)+'{0:02x}'.format(cmd_param2)+'","length":'+str(cmd_len)+'}}'
            else:
                request = '{"id":9,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"'+cmd_code+'","length":'+str(cmd_len)+'}}'
            self.logger.debug("Request to line: " + str(request))
            response = self.send_rainbird_command(request)
            return response.rstrip('\x00')

    class RainbirdEncryption:

      def __init__(self):
            self.BLOCK_SIZE= 16
            self.INTERRUPT = '\x00'
            self.PAD = '\x10'
            
      def AddPadding(self,data):
           new_data = data
           new_data_len = len(new_data)
           remaining_len = self.BLOCK_SIZE - new_data_len
           to_pad_len = remaining_len % self.BLOCK_SIZE
           pad_string = self.PAD * to_pad_len
           return ''.join([new_data, pad_string])
         
      def decrypt (self, encrypteddata, decryptkey):
           iv = bytes(encrypteddata[32:48])
           encrypteddata = bytes(encrypteddata[48:len(encrypteddata)])

           m = SHA256.new()
           m.update(bytes(decryptkey,"UTF-8"))

           symmetric_key = m.digest()
           symmetric_key = symmetric_key[:32]

           aes_decryptor = AES.new(symmetric_key, AES.MODE_CBC, iv)
           return aes_decryptor.decrypt(encrypteddata)

      def encrypt (self, data, encryptkey):
           tocodedata = data + '\x00\x10'
           m = SHA256.new()
           m.update(bytes(encryptkey,"UTF-8"))
           b = m.digest()
           iv = Random.new().read(16)
           c = bytes(self.AddPadding(tocodedata),"UTF-8")
           m = SHA256.new()
           m.update(bytes(data,"UTF-8"))
           b2 = m.digest()
           
           eas_encryptor = AES.new(b,AES.MODE_CBC, iv)
           encrypteddata = eas_encryptor.encrypt(c)
           return b2+iv+encrypteddata;

"""
logging.basicConfig(filename='pypython.log',level=logging.DEBUG)

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

controller = RainbirdController()
controller.setConfig("####IP####","####PASS####")
controller.startIrrigation(4,5)
time.sleep(4)
controller.stopIrrigation()

controller.currentRainSensorState()
"""