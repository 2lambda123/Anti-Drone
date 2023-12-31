import cv2
from threading import Thread
import time
import numpy as np
import sys
import time
import threading
import imagezmq
import numpy as np
from datetime import datetime
import imutils
import math
from fcm import fcm


class WebcamVideoStream:

    # 이미지 허브 새성
    imageHub = imagezmq.ImageHub('tcp://*:5555')
    send_address = 0
    sender = None
    Capture_Time = 20

    def __init__(self):
        print("init")

        self.fcm1 = fcm("dM4Tyq6_QiaWGRT3rvgMx5:APA91bERqNtgqXwNeuRUCM7ZryDSVZGbAxhKQVuMnBw0V6y4482TZJD0Kw9XCASEUGQu3D-Q0LNVciZ73vQpm2Cd9Jt6HEM-hp51b0dkmZ2je0eIlw5WaQf10tjXpxezHB0twkD00GP8")
        self.lastActive = {}

        self.lastActiveCheck = datetime.now()
        self.ESTIMATED_NUM_PIS = 4
        self.ACTIVE_CHECK_PERIOD = 10
        self.ACTIVE_CHECK_SECONDS = self.ESTIMATED_NUM_PIS * self.ACTIVE_CHECK_PERIOD

        self.w = 0
        self.h = 0

        self.Dronedata = []
        self.rpiName = None
        self.frame = cv2.imread('no_signal.jpg')
        self.frame = imutils.resize(self.frame, width=400)
        self.stopped = False

    camList = ['cam1','cam2','cam3','cam4']

    rectangule_color = (10, 0, 255)
    boxthickness = 3
    map_shape = (400, 400)

    # Auto_mode가 True이면 자동으로 드론 트래킹, 각각 좌우의 라즈베리파이와 상호작용하여 모터 컨트롤
    Auto_mode = True

    # 각각의 카메라의 좌우에 어떤 카메라가 있는지 카메라 배치를 나타냅니다. 
    Cam_left_right = {
        'cam1':['None', 'cam2'],
        'cam2':['cam1', 'cam3'],
        'cam3':['cam2', 'cam4'],
        'cam4':['cam3', 'None']    
    }
    Lastcapture_Time = { cam : datetime.now() for cam in camList} 

    # 각각의 라즈베리파이를 수동 컨트롤 하기 위한 딕셔너리
    Control_Dict = { cam : 'None' for cam in camList} 

    # 카메라 고정 위치
    Start_Point_Dict = {
        'cam1':(100,250),
        'cam2':(200,250),
        'cam3':(300,250),
        'cam4':(400,250),
    }

    # 초기 기준 각도 90도로 고정   3시 방향 부터 0도, 12시 방향 90도, 9시 180도, 6시 270도
    Angle_dict = { cam : 90 for cam in camList} 

    # index 0 : drone number, index 1 : ymin, index 2 : xmin, index 3: ymax, index 4 : xmax
    # index 5 : score, index 6 : pulse(pan, tilt), index 7 : distance
    Dronedata_Dict = {}
    Dnum_Dcit = {}
    # 각각의 라즈베리파이별 Frame 따로 관리  
    frameDict = {}
    
    def start(self):
        print("start thread")
        t = Thread(target=self.update, args=())
        t.daemon = True
        t.start()
        return self
    
    def update(self):
        print("read")
        while True:
            if self.stopped:
                return
            
            # 라즈베리파이에서 데이터를 읽어옴  
            (self.Dronedata, self.rpiName, self.frame) = self.imageHub.recv_image()

            # Auto_mode에 맞는 모터 컨트롤 문자로 응답(Res)  
            if self.Auto_mode == True:
                self.Control_Dict[self.rpiName] = self.Control_Cam(self.rpiName)
                self.imageHub.send_reply(self.Control_Dict[self.rpiName].encode())
            elif self.Control_Dict[self.rpiName] != 'None':
                self.imageHub.send_reply(self.Control_Dict[self.rpiName].encode())
                self.Control_Dict[self.rpiName] = 'None'
            else:
                self.imageHub.send_reply(self.Control_Dict[self.rpiName].encode())
            #self.imageHub.send_reply('True 0 0'.encode())

            # Dronedata를 각 라즈베리파이 따로 관리, 업데이트
            if self.rpiName not in self.Dronedata_Dict:
                self.Dnum_Dcit[self.rpiName] = 0
            else:    
                self.Dnum_Dcit[self.rpiName] = int(self.Dronedata_Dict[self.rpiName][0])
            self.Dronedata_Dict[self.rpiName] = self.Dronedata
            #self.Send_fcm(self.rpiName)
            #self.send_frame(self.rpiName)

            if self.rpiName not in self.lastActive.keys():
                print("[INFO] receiving data from {}...".format(self.rpiName))
            
            # 라즈파이별 마지막 요청 시간 관리, 업데이트
            self.lastActive[self.rpiName] = datetime.now()
            
            (self.h, self.w) = self.frame.shape[:2]

            # 각 라즈베리별 Frame 관리, 업데이트
            self.frameDict[self.rpiName] = self.frame

            cv2.waitKey(1)
            
            # 정해진 시간마다 연결이 끊어진 라즈베리파이가 있나 확인
            if (datetime.now() - self.lastActiveCheck).seconds > self.ACTIVE_CHECK_SECONDS:
                for (rpiName, ts) in list(self.lastActive.items()):
                    # 연결이 끊어졌다고 판단되는 시간이 넘어가면 pop
                    if (datetime.now() - ts).seconds > self.ACTIVE_CHECK_SECONDS:
                        print("[INFO] lost connection to {}".format(rpiName))
                        self.lastActive.pop(rpiName)
                        self.frameDict.pop(rpiName)
                        self.Dronedata_Dict.pop(rpiName)
                self.lastActiveCheck = datetime.now()

    
    def Send_fcm(self, name):
        if name in self.Dronedata_Dict:
            if int(self.Dronedata_Dict[name][0]) != self.Dnum_Dcit[name]:
                t = Thread(target=self.fcm1.sendMessage, args=())
                t.daemon = True
                t.start()
                

    # Auto_mode일 때 드론을 컨트롤하는 문자를 바꿔주는 함수
    # 자신의 왼쪽, 오른쪽 라즈베리파이를 비교하여 드론이 발견된 방향으로 회전하라는 문자로 바꿈
    # '(Auto_mode) (왼쪽or오른쪽 방향) (높이 각도)' 공백으로 구분 
    def Control_Cam(self, name):
        if name in self.Cam_left_right:
            left = self.Cam_left_right[name][0]
            right = self.Cam_left_right[name][1]
            left_dnum = 0
            right_dnum = 0
            
            if left in self.Dronedata_Dict:
                left_dnum = self.Dronedata_Dict[left][0]
            if right in self.Dronedata_Dict:
                right_dnum = self.Dronedata_Dict[right][0]
            
            if left_dnum == right_dnum:
                if left_dnum == 0:
                    return 'True 0 0'
                elif max(self.Dronedata_Dict[left][5]) > max(self.Dronedata_Dict[right][5]):
                    return 'True L ' + str(self.Dronedata_Dict[left][6][1])
                elif max(self.Dronedata_Dict[right][5]) < max(self.Dronedata_Dict[left][5]):
                    return 'True R ' + str(self.Dronedata_Dict[right][6][1])
                else:
                    return 'True 0 0'
            elif left_dnum > right_dnum and self.Dronedata_Dict[left][6][0]:
                return 'True L ' + str(self.Dronedata_Dict[left][6][1])
            elif left_dnum < right_dnum and self.Dronedata_Dict[right][6][0]:
                return 'True R ' + str(self.Dronedata_Dict[right][6][1])
            else:
                return 'True 0 0'
        else:
            return 'True 0 0'
            

    # 수동모드인 경우 모터 컨트롤 
    # '(Auto_mode) 방향' 공백으로 구분
    @classmethod
    def move_Up(cls, name):
        if name in cls.Control_Dict and cls.Auto_mode == False:
            cls.Control_Dict[name] = 'False U' # 위 
        print('U')
        
    
    @classmethod
    def move_Down(cls, name):
        if name in cls.Control_Dict and cls.Auto_mode == False:
            cls.Control_Dict[name] = 'False D' # 아래
        print('D')
        
    
    @classmethod
    def move_Right(cls, name):
        if name in cls.Control_Dict and cls.Auto_mode == False:
            cls.Control_Dict[name] = 'False R' # 오른쪽
        print('R')
        

    @classmethod
    def move_Left(cls, name):
        if name in cls.Control_Dict and cls.Auto_mode == False:
            cls.Control_Dict[name] = 'False L' # 왼쪽
        print('L')
        
    @classmethod
    def move_Init(cls, name):
        if name in cls.Control_Dict and not cls.Auto_mode:
            cls.Control_Dict[name] = 'False C' # 원점으로 
        print('C')
    
    # 해당하는 라즈베리파이의 Frame을 읽고, cv2로 바운딩 박스 및 Text를 그려서 return
    @classmethod
    def get_frame(cls, name):
        if name in cls.frameDict:
            frame = cls.frameDict[name].copy()
            if int(cls.Dronedata_Dict[name][0]) > 0:
                scores = list(map(float, cls.Dronedata_Dict[name][5]))
                ymin = list(map(int, cls.Dronedata_Dict[name][1]))
                xmin = list(map(int, cls.Dronedata_Dict[name][2]))
                ymax = list(map(int, cls.Dronedata_Dict[name][3]))
                xmax = list(map(int, cls.Dronedata_Dict[name][4]))

                # 십자 라인 그리기 (트래킹 하는 드론 표시)
                most = scores.index(max(scores))
                most_ymin = ymin[most]
                most_xmin = xmin[most]
                most_ymax = ymax[most]
                most_xmax = xmax[most]
                x_medium = int((most_xmin+most_xmax)/2)
                y_medium = int((most_ymin+most_ymax)/2)
                rows, cols, _ = frame.shape
                cv2.line(frame, (x_medium, 0), (x_medium, rows), cls.rectangule_color, 2)
                cv2.line(frame, (0, y_medium), (cols, y_medium), cls.rectangule_color, 2)

                for i in range(len(scores)):
                    if ((scores[i] > 0.5) and (scores[i] <= 1.0)):
                        
                        # 바운딩 박스 그리기
                        if i == most:
                            cv2.rectangle(frame, (xmin[i],ymin[i]), (xmax[i],ymax[i]), cls.rectangule_color, cls.boxthickness)  #xmax = x+w ymax = y+h
                        else:
                            cv2.rectangle(frame, (xmin[i],ymin[i]), (xmax[i],ymax[i]), (0,255,255), cls.boxthickness)  #xmax = x+w ymax = y+h 
                        
                        label = '%s: %d%%' % ('Drone', int(scores[i]*100)) # 드론일 확률 나타냄
                        labelSize, baseLine = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2) # Get font size
                        label_ymin = max(ymin[i], labelSize[1] + 10) 
                        # 라벨이 들어갈 박스 그리기
                        cv2.rectangle(frame, (xmin[i], label_ymin-labelSize[1]-10), (xmin[i]+labelSize[0], label_ymin+baseLine-10), (255, 255, 255), cv2.FILLED) 
                        # 라벨 putText
                        cv2.putText(frame, label, (xmin[i], label_ymin-7), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2) 
                    
            # 몇 번째 카메라인지 putText
            cv2.putText(frame, name, (380, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            # resize
            frame = imutils.resize(frame, width=400)
            return frame
        else:          # 해당하는 라즈베리파이가 없으면 no_signal 이미지 return 
            default_frame = cv2.imread('no_signal.jpg')
            default_frame = imutils.resize(default_frame, width=400)
            return default_frame

    # 해당하는 라즈베리파이에서 발견된 드론의 수를 return 
    @classmethod
    def get_dnum(cls, name):
        if name in cls.Dronedata_Dict:
            return int(cls.Dronedata_Dict[name][0])
        else:
            return 0    

    # 해당하는 라즈베리파이에서 발견된 드론 중 가장 확률이 높은 드론의 거리를 return 
    @classmethod
    def get_distance(cls, name):
        if name in cls.Dronedata_Dict:
            return float(cls.Dronedata_Dict[name][7])
        else:
            return 0

    # 실질적인 이미지 전송
    @classmethod
    def send(cls, name):
        print('send img', name)
        #mem = cls.sender.send_image(0, name, cls.frameDict[name])
        try:
            mem = cls.sender.send_image(list(cls.Dronedata_Dict[name]), name, cls.frameDict[name])
        except Exception as e: 
            message = "Exception({0}): {1}".format(e.errno, e.strerror)
            print(message)
            pass 

    # 해당하는 라즈베리파이의 이미지와 모델에서 출력한 드론 위치 정보를 이미지 저장하는 컴퓨터로 전송
    @classmethod
    def send_frame(cls, name):
        if name in cls.Dronedata_Dict and cls.sender != None:
            if int(cls.Dronedata_Dict[name][0]) > 0 and (datetime.now() - cls.Lastcapture_Time[name]).seconds > cls.Capture_Time: 
                print('send img')
                t = Thread(target=WebcamVideoStream.send, args=(name,))
                t.daemon = True
                t.start()
                cls.Lastcapture_Time[name] = datetime.now()     

    @classmethod
    def set_address(cls, address):
        if address != 0:
            cls.send_address = address
            cls.sender = imagezmq.ImageSender("tcp://{}:5001".format(cls.send_address))


    # AutoMode 변경 
    @classmethod
    def AutoMode_Flag(cls):
        if cls.Auto_mode == True:
            cls.Auto_mode = False
        else:
            cls.Auto_mode = True
        return cls.Auto_mode

    @classmethod
    def Radar_map(cls):
        img = cv2.imread('board.jpg')
        img = cv2.resize(img, (500,500))
        for name in cls.camList:    
            if name in cls.Dronedata_Dict:
                r = 300
                center = (int(cls.Dronedata_Dict[name][6][0])-200)*180/490 + cls.Angle_dict[name]
                x_start = cls.Start_Point_Dict[name][0]
                y_start = cls.Start_Point_Dict[name][1]
                x_left = int(x_start + r*np.sin(math.radians(-30+center)))
                y_left = int(y_start + r*np.cos(math.radians(-30+center)))
                x_right = int(x_start + r*np.sin(math.radians(30+center)))
                y_right = int(y_start + r*np.cos(math.radians(30+center)))
                cv2.line(img, (x_start,y_start), (x_left,y_left), (0,255,0),1, cv2.LINE_AA)
                cv2.line(img, (x_start,y_start), (x_right,y_right), (0,255,0),1, cv2.LINE_AA)
                if cls.Dronedata_Dict[name][0] > 0:
                    distance = int(cls.Dronedata_Dict[name][7]*150)
                    x_center = int(x_start + distance*np.sin(math.radians(center)))
                    y_center = int(y_start + distance*np.cos(math.radians(center)))
                    cv2.line(img, (x_center, y_center),(x_center, y_center),(0,255,0),5)
        return img

            
    def stop(self):
        self.stopped = True
    

