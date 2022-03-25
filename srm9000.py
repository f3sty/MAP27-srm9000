#!/usr/bin/env python3
import serial
import binascii
import time
from crccheck.crc import Crc16Usb, Crc16Modbus
import re
import argparse
import sys

global connected
connected = False
loggedIn = False
lastAction = ''
seq = 0

def pktType(id):
    switch={
        b'\x01':'LR',
        b'\x02':'ACK',
        b'\x04':'LT'
        }
    return switch.get(id, "ERR")

def CRC(body_):
    return (Crc16Usb.calchex(body_, byteorder='little'))

def readPkt():
  global connected
  global seq
  global lastAction
  global loggedIn
  foo = ser.read_until(expected=b'\x16\x10\x02')
  s = b'\x16\x10\x02' + ser.read_until(expected=b'\x10\x03')
  if s == b'\x16\x10\x02':
      print('timeout')
      return

  cs = ser.read(2)
  header = s[0:3]
  RXbody = s[3:]
  body = re.sub(b'\x10\x10',b'\x10', RXbody)
  res = binascii.hexlify(cs)
  cs_in = body
  csb = CRC(body)
  if csb != res.decode('ASCII'):
    print("crc fail - ", end='')
    print(res, end=' ')
    print(csb)

  if pktType(body[:1]) == 'LR':
      sendLR()

  if pktType(body[:1]) == 'ACK':
      if connected == False:
          print("Connecting ", end='')
          print(binascii.hexlify(body[1:2]))
          sendLA(body[1:2])
          connected = True
          return

      elif lastAction == 'login':
          loggedIn = True
          print("Login successful")
          lastAction = ''
          seq_ = int.from_bytes(body[1:2], byteorder='big')

      elif lastAction == 'status':
          requestVolume(int.from_bytes(body[1:2], byteorder='big'))

      else:
          requestStatus(int.from_bytes(body[1:2], byteorder='big'))
      return



  if pktType(body[:1]) == 'LT':
      # link transfer packet
      if body[5:6] == b'\x96':
        connected = True 
        print("Logging in!")
        login_msg = b'\x00\xB5\x00\x00\x00\x03\x06\x03\x45\x10\x03'
        seq = 1
        sendLT(seq, login_msg)
        lastAction = 'login'
        time.sleep(0.01)
        sendLA(b'\x02')

      elif body[5:6] == b'\x9B':
        stateReport9B(body)
        return

      elif body[5:6] == b'\x9C':
        volReport9C(body)
        return

  return

def requestStatus(seq):
    global lastAction
    sendLT(seq, b'\x00\xB9\x00\x10\x03')
    lastAction = 'status'
    return

def requestVolume(seq):
    global lastAction
    sendLT(seq, b'\x00\xBA\x03\x10\x03')
    lastAction = 'vol'
    return

def volReport9C(msgbody):
    print("--------------------------------")
    print("Volume Report: ", binascii.hexlify(msgbody))
    nVolume = int.from_bytes(msgbody[6:7], byteorder='big')
    aVolume = int.from_bytes(msgbody[7:8], byteorder='big')
    dVolume = int.from_bytes(msgbody[8:9], byteorder='big')
    if aVolume > 31:
        aVolume = aVolume - 255
    print('volume: ', nVolume, '  Alert offset: ', aVolume, '  Data volume: ', dVolume)
    sendLA(incByte(msgbody[1:2]))
    return
    

def stateReport9B(msgbody):
    print("--------------------------------")
    print("Status Report: ", binascii.hexlify(msgbody))
    LowPower = msgbody[7]>>4 & 1
    DualWatch = msgbody[7]>>1 & 1
    Tx = msgbody[8]>>4 & 1
    ValidSignal = msgbody[8]>>7 & 1
    RSSI = -130 + msgbody[9]
    Channel = msgbody[11]

    print("CH ", Channel, ", RSSI: ", RSSI, ", Tx: ", Tx, ", LP: ", LowPower, ", Dual watch: ", DualWatch, ", Valid signal: ", ValidSignal)
    sendLA(incByte(msgbody[1:2]))
    return


def sendLT(LTseq, LTmsg):
    seq_ = bytes([LTseq])
    LTheader = b'\x04' + bytes([LTseq]) + b'\x01\x00'
    LTpkt = LTheader +  LTmsg
    cs_ = Crc16Usb.calcbytes(LTpkt, byteorder='little')
    LTheader = re.sub(b'\x10', b'\x10\x10', LTheader)
    LTmsg = re.sub(b'\x10', b'\x10\x10', LTmsg)
    LTmsg = re.sub(b'\x10\x10\x03', b'\x10\x03', LTmsg)
    ser.write(b'\x16\x10\x02')
    ser.write(LTheader)
    ser.write(LTmsg)
    ser.write(cs_)



def sendLA(nr):
    LAseq = int.from_bytes(nr, 'big')
    LApkt = b'\x02' + nr + b'\x01\x00\x10\x03'
    cs_ = Crc16Usb.calcbytes(LApkt, byteorder='little')
    LApkt = re.sub(b'\x10', b'\x10\x10', LApkt)
    LApkt = re.sub(b'\x10\x10\x03', b'\x10\x03', LApkt)
    ser.write(b'\x16\x10\x02')
    ser.write(LApkt)
    ser.write(cs_)
    return

def sendLR():
    LRbody = b'\x01\x0E\x01\x01\x10\x03'
    cs_ = Crc16Usb.calcbytes(LRbody, byteorder='little')
    print('LR body: ',b'\x16\x10\x02', LRbody, cs_)
    ser.write(b'\x16\x10\x02')
    ser.write(LRbody)
    ser.write(cs_)
    return


def sendLogin():
    return


def incByte(inb):
    outi = (int.from_bytes(inb, 'big') + 1) % 256
    return(bytes([outi]))


parser = argparse.ArgumentParser()
parser.add_argument("--port", help="Set Serial device name", required=True)
args = parser.parse_args()
port = args.port.lstrip()

if re.match("/dev/", port) == None:
    print("Invalid port",port,"specified")
    sys.exit()

ser = serial.Serial(port, 19200, timeout=3)
ser.reset_input_buffer()

while True:
    rxbufcount = ser.inWaiting()
    if rxbufcount > 6:
        readPkt()
    else:
     time.sleep(0.3)

ser.close()
