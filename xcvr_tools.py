from jnpr.junos import Device
from jnpr.junos.exception import ConnectError
import argparse, datetime, threading, re, sys, time
from time import sleep

class CDC():
    def __init__(self, xcvr,desiredCDCdec=''):
        self.xcvr=xcvr
        vendor=self.xcvr.vendor.upper()[:-1]
        self.desiredCDCdec=desiredCDCdec

        if vendor == "JUNIPER-1T" and (self.xcvr.jpn == '740-131168' or self.xcvr.jpn == '740-131169'):
            self.vendor = vendor
        elif vendor == "JUNIPER-2E" and self.xcvr.jpn == '740-157138':
            self.vendor = vendor
        elif vendor == "JUNIPER-1A" and (self.xcvr.jpn == '740-151745' or self.xcvr.jpn == '740-179331'):
            self.vendor = vendor
        else:
            self.vendor = 'Unsupported'

    def signedHex_to_dec(self, signedHex):
        return  int((1 << 32) - int(signedHex,16))
    
    def dec_to_signedHex(self, dec):
        return hex((1 << 32) - int(dec))
    
    def unsignedHex_to_dec(self, unsignedHex):
        return int(unsignedHex,16)
    
    def dec_to_unsignedHex(self, dec, numberofBytes):
        return format(int(dec),f'#0{numberofBytes*2+2}x')
    
    def readCurrentCDCSettings(self, page, startAddress, numberofBytes):
        self.xcvr.changePage(page)
        currentCDChex=""
        for x in range(numberofBytes):
            currentCDChex=currentCDChex + self.xcvr.readReg(address=f'{startAddress + x}',y='',page=page)
        return currentCDChex
    
    def changeCurrentCDCsettings(self, page, startAddress, hexCDC):
        self.xcvr.changePage(page)
        numberofBytes=int((len(hexCDC)-2)/2)
        for x in range(numberofBytes):
            self.xcvr.writeReg(startAddress + x, f"0x{hexCDC[2*x+2:2*x+4]}",page=page)

    def JUNIPER_2E_multiplierChecker(self, product):
        multiplier = 0
        for x in range(2,int(pow(product,0.5))+ 1):
            if product % x == 0:
                if product//x < 65535:
                    multiplier = x
                    break
                else:
                    continue
        return multiplier
    
    def change(self):

        if self.vendor == 'Unsupported':
            return 'Unsupported'
        
        startTime = datetime.datetime.now().timestamp()
        moduleState=self.xcvr.checkModuleState()

        while  moduleState != '44' and moduleState != '55'and moduleState != '77':
            print(f'Waiting for DP to be activated, currently {moduleState[0]}. Time elapsed: {round(datetime.datetime.now().timestamp() - startTime)} seconds')
            moduleState=self.xcvr.checkModuleState()

        print(f"DP Activated ({moduleState[0]})! Deactivating DP.")
        self.xcvr.stopXcvrPeriodic()
        self.xcvr.dp_deinit()

        if self.vendor == 'JUNIPER-1T':
            self.QDD_400G_ZR_M_HP()
        elif self.vendor == 'JUNIPER-2E':
            self.JCO400_QDD_ZR_M()
        elif self.vendor == 'JUNIPER-1A':
            self.JCO400_QDD_ZR_M_HP()

        self.wrapUp(self.xcvr.currentCDC)

    def wrapUp(self, currentCDCdec):
        self.xcvr.dp_init()
        self.xcvr.startXcvrPeriodic()
        if  int(currentCDCdec) == self.desiredCDCdec:
            print("Max CDC configuration succeeded! Please wait for link-up. ~ 2 mins")
        else:
            sys.exit("Max CDC configuration Failed. Please Try Again")

        intStatus, moduleFault = self.xcvr.intStatus()
        startTime = datetime.datetime.now().timestamp()
        timeout=300
        sleepTime=5
        print(f"Waiting for Link Up. Timeout is {timeout} seconds")
        while intStatus.lower() == "down":
            if moduleFault:
                response = input("Module is in Fault State. Do you want to perform soft OIR and try again? (y/n): ")
                if response.lower() == 'y':
                    self.xcvr.softOIR()
                    self.change()
                else:
                    sys.exit("Module Fault!")
            
            print(f"Waiting for Link Up.  Time elapsed: {round(datetime.datetime.now().timestamp() - startTime)} seconds. ")   
            intStatus, moduleFault = self.xcvr.intStatus() 
            sleep(sleepTime)

            if datetime.datetime.now().timestamp()  > startTime + timeout:
                sys.exit("Timeout!, Please try again.")

        if intStatus.lower() == 'up':
            print("Link Up!")

    def QDD_400G_ZR_M_HP(self,readOnly=False):
        
        if readOnly:
             currentCDChex=self.readCurrentCDCSettings('0xBA',188,4)
             return self.signedHex_to_dec(currentCDChex)

        print("Reading Current Max CDC Setting")
        currentCDChex=self.readCurrentCDCSettings('0xBA',188,4)
        self.xcvr.currentCDC=self.signedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is {self.xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {self.desiredCDCdec} ps/nm.")
        desiredCDChex=self.dec_to_signedHex(self.desiredCDCdec)
        self.changeCurrentCDCsettings('0xB8',200,desiredCDChex)

        print("Done! Verifying if accepted by the module.")
        currentCDChex=self.readCurrentCDCSettings('0xBA',188,4)
        self.xcvr.currentCDC=self.signedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is now {self.xcvr.currentCDC} ps/nm.")
    
    def JCO400_QDD_ZR_M(self,readOnly=False):
        if readOnly:
            self.xcvr.changePage('0x31')
            if self.xcvr.readReg(address='248',y='',page='0x31') == "01":
                currentCDChex=self.readCurrentCDCSettings('0x31',249,2)
                currentCDCmultiplier = self.unsignedHex_to_dec(self.xcvr.readReg(address='251',y='',page='0x31'))
            else:
                currentCDChex=self.readCurrentCDCSettings('0x31',252,2)
                currentCDCmultiplier = 10
            return self.unsignedHex_to_dec(currentCDChex) * currentCDCmultiplier
        
        print("Reading Current Max CDC Setting")
        self.xcvr.changePage('0x31')
        if self.xcvr.readReg(address='248',y='',page='0x31') == "01":
            currentCDChex=self.readCurrentCDCSettings('0x31',249,2)
            currentCDCmultiplier = self.unsignedHex_to_dec(self.xcvr.readReg(address='251',y='',page='0x31'))
        else:
            currentCDChex=self.readCurrentCDCSettings('0x31',252,2)
            currentCDCmultiplier = 10
        self.xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex) * currentCDCmultiplier
        print(f"Current Max CDC Setting is {self.xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {self.desiredCDCdec} ps/nm.")
        multiplier = 0
        if self.desiredCDCdec > 65535:
            multiplier=self.JUNIPER_2E_multiplierChecker(self.desiredCDCdec)
            if multiplier == 0:
                print("Desired Max CDC Setting is a prime number. Adding 1.")
                self.desiredCDCdec+=1
                multiplier=self.JUNIPER_2E_multiplierChecker(self.desiredCDCdec)
                print(f"Target Max CDC Setting is now {self.desiredCDCdec}")
        else:
            multiplier = 1
        self.xcvr.changePage('0x31')
        self.xcvr.writeReg('248','0x01',page='0x31')
        desiredCDChex=self.dec_to_unsignedHex(self.desiredCDCdec//multiplier,2)
        self.changeCurrentCDCsettings('0x31',249,desiredCDChex)
        self.xcvr.writeReg('251',self.dec_to_unsignedHex(multiplier,1),page='0x31')
        self.xcvr.dp_applyInitLane()

        print("Done! Verifying if accepted by the module.")
        self.xcvr.changePage('0x31')
        if self.xcvr.readReg(address='248',y='',page='0x31') == "01":
            currentCDChex=self.readCurrentCDCSettings('0x31',249,2)
            currentCDCmultiplier = self.unsignedHex_to_dec(self.xcvr.readReg(address='251',y='',page='0x31'))
        else:
            currentCDChex=self.readCurrentCDCSettings('0x31',252,2)
            currentCDCmultiplier = 10
        self.xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex) * currentCDCmultiplier
        print(f"Current Max CDC Setting is now {self.xcvr.currentCDC} ps/nm.")

    def JCO400_QDD_ZR_M_HP(self,readOnly=False):
        
        if readOnly:
            currentCDChex=self.readCurrentCDCSettings('0x1E',0x80,4)
            return self.unsignedHex_to_dec(currentCDChex)

        print("Reading Current Max CDC Setting")
        currentCDChex=self.readCurrentCDCSettings('0x1E',0x80,4)
        self.xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is {self.xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {self.desiredCDCdec} ps/nm.")
        self.xcvr.changePage('0x1E')
        self.xcvr.writeReg('0x84','0x01',page='0x1E')
        desiredCDChex=self.dec_to_unsignedHex(self.desiredCDCdec,4)
        self.changeCurrentCDCsettings('0x1E',0x80,desiredCDChex)
        self.xcvr.dp_applyInitLane()

        print("Done! Verifying if accepted by the module.")
        currentCDChex=self.readCurrentCDCSettings('0x1E',0x80,4)
        self.xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is now {self.xcvr.currentCDC} ps/nm.")

    def read(self):
        if self.vendor == 'Unsupported':
            return 'Unsupported'
        self.xcvr.stopXcvrPeriodic()
        if self.vendor == 'JUNIPER-1T':
            return self.QDD_400G_ZR_M_HP(readOnly=True)
        elif self.vendor == 'JUNIPER-2E':
            return self.JCO400_QDD_ZR_M(readOnly=True)
        elif self.vendor == 'JUNIPER-1A':
            return self.JCO400_QDD_ZR_M_HP(readOnly=True)
        self.xcvr.startXcvrPeriodic()

class Xcvr():
    def __init__(self, interface, dev):
        self.interface = interface
        self.dev = dev

        if 'not found' in self.dev.rpc.get_interface_information({'format':'text'},interface_name=self.interface).text.lower():
            if 'not found' in self.dev.rpc.get_interface_information({'format':'text'},interface_name=f"{self.interface}:0").text.lower():
                sys.exit("Interface Name not found") 
            else:
                self.interface=f"{self.interface}:0"

        if not self.xcvrPresent():
            sys.exit("Transceiver is absent!")
        self.fpc, self.pic, self.port = self.parseInt(interface)
        self.jpn, self.vendor, self.description = self.checkModuleInfo()

    def parseInt(self, interface):
        parsedInt = re.search(r'-(\d+)\/(\d+)\/(\d+)', interface)
        if parsedInt:
            _fpc = parsedInt.group(1)
            _pic = parsedInt.group(2)
            _port = parsedInt.group(3)
            return _fpc, _pic, _port
        
    def xcvrPresent(self):
        intInfo=self.dev.rpc.get_interface_information(interface_name=self.interface,normalize=True)
        deviceFlags=intInfo.findall(f'physical-interface/if-device-flags/')
        for deviceFlag in deviceFlags: 
            if 'ifdf-xcvr-absent' in deviceFlag.tag:
                self.xcvrPresent=False
            else:
                self.xcvrPresent=True
        return self.xcvrPresent
    
    def checkModuleState(self,y=''):
        global returnResults
        self.stopXcvrPeriodic()
        self.changePage('0x11')
        val = self.readReg(address='0x80',y='',page='0x11')
        self.startXcvrPeriodic()
        if y!='':
            returnResults[y]=val
        return val
    
    def stopXcvrPeriodic(self):
        self.xcvrPeriodicRunning = False
        return self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  xcvr_periodic_stop", target=f"fpc{self.fpc}", timeout="1")

    def startXcvrPeriodic(self):
        self.xcvrPeriodicRunning = True
        return self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  xcvr_periodic_start", target=f"fpc{self.fpc}", timeout="1")
    
    def changePage(self, page):
        return self.writeReg('0x7f', page, page=page)

    def writeReg(self, address, value, page =""):
        result = self.dev.rpc.request_pfe_execute(command=f"test picd optics write fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} address {address} value {value}", target=f"fpc{self.fpc}", timeout="1")
        if page != "":
            result = self.dev.rpc.request_pfe_execute(command=f"test picd optics write fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} page {page} address {address} value {value}", target=f"fpc{self.fpc}", timeout="1")
        return result.text
    
    def readReg(self, address,y='',page=''):
        global returnResults
        
        val=self.dev.rpc.request_pfe_execute(command=f"test picd optics read fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} address {address}", target=f"fpc{self.fpc}", timeout="1")
        match = re.findall(r'Val: 0x([0-9,a-f]+)',val.text)
        if not match and page != '':
            val=self.dev.rpc.request_pfe_execute(command=f"test picd optics read fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} page {page} address {address}", target=f"fpc{self.fpc}", timeout="1")
            match = re.findall(r'Val: 0x([0-9,a-f]+)',val.text)
        if not match:
            sys.exit(f"Failed to read address {address} (page {page}): {val.text.strip()}")
        val = match[0]
    
        if len(val) == 1:
            result = '0' + val
        else:
            result =  val

        if y!='':
            returnResults[y]=result
        return result

    def checkModuleInfo(self):
        picDetail=self.dev.rpc.get_pic_detail(normalize=True,fpc_slot=self.fpc,pic_slot=self.pic)
        jpn=picDetail.find(f'fpc/pic-detail/port-information/port/[port-number="{self.port}"]/sfp-vendor-pno').text
        vendor = picDetail.find(f'fpc/pic-detail/port-information/port/[port-number="{self.port}"]/sfp-vendor-name').text
        description = self.dev.rpc.get_chassis_inventory(normalize=True).find(f'chassis/chassis-module[name="FPC {self.fpc}"]/chassis-sub-module[name="PIC {self.pic}"]/chassis-sub-sub-module[name="Xcvr {self.port}"]/description').text
        return jpn,vendor, description
    
    def dp_deinit(self,changeCDC=True):
        if not changeCDC:
            self.stopXcvrPeriodic()
        
        self.changePage('0x10')
        self.writeReg('0x82','0xff',page='0x10')
        self.writeReg('0x80','0xff',page='0x10')                
        sleep(3)

        if not changeCDC:
            self.startXcvrPeriodic()
        
    def dp_init(self,changeCDC=True):
        if not changeCDC:
            self.stopXcvrPeriodic()

        self.changePage('0x10')
        self.writeReg('0x80','0x00',page='0x10')
        self.writeReg('0x82','0x00',page='0x10')
        sleep(3)
        
        if not changeCDC:
            self.startXcvrPeriodic()
    
    def dp_reinit(self):
        self.stopXcvrPeriodic()
        self.dp_deinit()
        sleep(1)
        self.dp_init()
        self.startXcvrPeriodic()

    def softOIR(self):
        self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  oir_enable", target=f"fpc{self.fpc}", timeout="1")
        self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  remove", target=f"fpc{self.fpc}", timeout="1")
        sleep(3)
        self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  insert", target=f"fpc{self.fpc}", timeout="1")
        self.dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  oir_disable", target=f"fpc{self.fpc}", timeout="1")
    
    def dp_applyInitLane(self):
        self.changePage('0x10')
        self.writeReg('143','0xff',page='0x10')
    
    def changeRXThreshold(self,alarm='',y=''):
        global returnResults
        supported=False
        
        self.stopXcvrPeriodic()
        if self.jpn == '740-131168' or self.jpn == '740-131169' or self.jpn == '740-157138' or self.jpn == '740-151745':
            supported=True
        else:
            result = "NOT SUPPORTED"

        if alarm == 'DSPLOL' and supported:
            if 'JUNIPER-1A' in self.vendor:
                self.changePage('0x1E')
                self.writeReg('133','0x2',page='0x1E')
                result = "SUCCESS"
            else:
                result = "NOT SUPPORTED"

        elif alarm != '' and supported:
            self.changePage('0x30')
            alarm_hex=str(hex((1 << 32) +int(alarm)))[-4:]
            self.writeReg('130',f'0x{alarm_hex[:-2]}',page='0x30')
            self.writeReg('131',f'0x{alarm_hex[-2:]}',page='0x30')
            self.writeReg('138',f'0x{alarm_hex[:-2]}',page='0x30')
            self.writeReg('139',f'0x{alarm_hex[-2:]}',page='0x30')
            warn_hex=str(hex((1 << 32) +int(alarm)+1))[-4:]
            self.writeReg('134',f'0x{warn_hex[:-2]}',page='0x30')
            self.writeReg('135',f'0x{warn_hex[-2:]}',page='0x30')
            self.writeReg('142',f'0x{warn_hex[:-2]}',page='0x30')
            self.writeReg('143',f'0x{warn_hex[-2:]}',page='0x30')
            result = "SUCCESS"

        self.startXcvrPeriodic()
        
        if y!='':
            returnResults[y]=result
        return result


    def rxSquelchStatus(self,y=''):
        global returnResults
        self.stopXcvrPeriodic()
        self.changePage('0x10')
        result = self.readReg(address='139',y='',page='0x10')
        self.startXcvrPeriodic()
        if y!='':
            returnResults[y] = result
        return result

    def intStatus(self):
        intInfo=self.dev.rpc.get_interface_information(interface_name=self.interface,normalize=True)
        self.operStatus=intInfo.find(f'physical-interface/oper-status').text
        deviceFlags=intInfo.findall(f'physical-interface/if-device-flags/')
        for deviceFlag in deviceFlags: 
            if 'ifdf-xcvr-error' in deviceFlag.tag:
                self.xcvr_error = True
            else:
                self.xcvr_error = False
        return self.operStatus, self.xcvr_error
    
    def changeCDC(self,desiredCDCdec):
        desiredCDCdec=int(desiredCDCdec)
        xcvr_configurator=CDC(self,desiredCDCdec)
        xcvr_configurator.change()

    def readCDC(self,y=''):
        global returnResults
        xcvr_configurator=CDC(self)
        result =  xcvr_configurator.read() 
        if y!='':
            returnResults[y]=result
        return result

def initializeDevices(y):
    global interfaces, dev
    dev[y]=Device().open()
    interfaces[y]=Xcvr(ints[y],dev[y])
    
if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Xcvr tools")
    arg_parser.add_argument(('--interface'),required=True, help="Interface Name or all")
    arg_parser.add_argument(('--command'),required=True, help="checkCDC,changeCDC,checkRxSquelch,checkDP,softOIR,dpReset,dpDeinit,dpInit,readReg,writeReg,xcvrPeriodicStop,xcvrPeriodicStart")
    arg_parser.add_argument(('--page'),required=False, help="page")
    arg_parser.add_argument(('--max_cdc'),required=False, help="Target Max CDC")
    arg_parser.add_argument(('--address'),required=False, help="address")
    arg_parser.add_argument(('--value'),required=False, help="value")
    arg_parser.add_argument(('--rxLOSthreshold'),required=False, help="rxLOSthreshold")
    args = arg_parser.parse_args() 
    try:
        devMain=Device().open()
        dev=[]
    except ConnectError as err:
        print ("Cannot connect to device: {0}".format(err))
        sys.exit(1)
    except Exception as err:
        print (err)
        sys.exit(1)
    ints=[]

    if args.interface=='all':
        tree=devMain.rpc.get_chassis_inventory(normalize=True).getroottree()
        for element in tree.iterfind('//chassis-module/name'):
            if 'FPC' in element.text:
                fpc=element.text
                for fpcSibling in element.itersiblings(tag='chassis-sub-module'):
                    for picSibling in fpcSibling.iterchildren(tag='name'):
                        if 'PIC' in picSibling.text:
                            pic=picSibling.text
                            for portSibling in picSibling.itersiblings(tag='chassis-sub-sub-module'):
                                if 'Xcvr' in portSibling.find('name').text:
                                    port=portSibling.find('name').text
                                    fpc= re.search(r'\d+',fpc)[0]
                                    pic=re.search(r'\d+',pic)[0]
                                    port=re.search(r'\d+',port)[0]
                                    ints.append(f'et-{fpc}/{pic}/{port}')
        interfaces=[0]*len(ints)
        intThreads=[0]*len(ints)
        dev=[0]*len(ints)
        for y in range(len(ints)):
            intThreads[y]=(threading.Thread(target=initializeDevices,args=(y,)))
            intThreads[y].start()
        for y in range(len(ints)):
            intThreads[y].join()
    else:
        interfaces=[(Xcvr(args.interface,devMain))]
   
    returnResults=[0]*len(interfaces)
    
    try:
        if args.command == 'checkCDC':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].readCDC,args=(y,)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                if returnResults[y] != 'Unsupported':
                    print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - {returnResults[y]:7} ps/nm')
                else:
                    print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} -    UNSUPPORTED')
        elif args.command == 'changeCDC':
            if args.interface == 'all':
                sys.exit('Simulataneous CDC Setting not yet supported.')
            else:
                interfaces[0].changeCDC(int(args.max_cdc))

        elif args.command == 'checkRxSquelch':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].rxSquelchStatus,args=(y,)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - 0x{returnResults[y]}')

        elif args.command == 'checkDP':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].checkModuleState,args=(y,)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - 0x{returnResults[y]}')

        elif args.command == 'softOIR':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].softOIR))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')
        
        elif args.command == 'dpReset':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].dp_reinit))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')
        
        elif args.command == 'dpDeinit':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].dp_deinit,args=(False,)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')

        elif args.command == 'dpInit':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].dp_init,args=(False,)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')
                
        elif args.command == 'xcvrPeriodicStop':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].stopXcvrPeriodic))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')
        
        elif args.command == 'xcvrPeriodicStart':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].startXcvrPeriodic))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - SUCCESS')

        elif args.command == 'changeRXThreshold':
            threads=[]
            for y in range(len(interfaces)):
                threads.append(threading.Thread(target=interfaces[y].changeRXThreshold,args=(args.rxLOSthreshold,y)))
                threads[y].start()
            for y in range(len(interfaces)):
                threads[y].join()
            for y in range(len(interfaces)):
                print(f'{interfaces[y].interface:11} - {interfaces[y].jpn:12} - {interfaces[y].description:30} - {returnResults[y]}')
        else:
            sys.exit("Invalid Command!")

    except Exception as error:
        print(error)
        sys.exit("Script failed")