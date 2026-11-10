from jnpr.junos import Device
from jnpr.junos.exception import ConnectError
import argparse
import re
import sys
from lxml import etree
from time import sleep
import datetime

class Xcvr:
    def __init__(self, interface):
        self.interface = interface
        self.currentPage = ''
        if not self.xcvrPresent():
            sys.exit("Transceiver is absent!")
        self.fpc, self.pic, self.port = self.parseInt(interface)
        self.jpn, self.vendor = self.checkModuleInfo()

    def parseInt(self, interface):
        parsedInt = re.search(r'-(\d+)\/(\d+)\/(\d+)', interface)
        if parsedInt:
            _fpc = parsedInt.group(1)
            _pic = parsedInt.group(2)
            _port = parsedInt.group(3)
            return _fpc, _pic, _port
        
    def xcvrPresent(self):
        intInfo=dev.rpc.get_interface_information(interface_name=self.interface,normalize=True)
        deviceFlags=intInfo.findall(f'physical-interface/if-device-flags/')
        for deviceFlag in deviceFlags: 
            if 'ifdf-xcvr-absent' in deviceFlag.tag:
                self.xcvrPresent=False
            else:
                self.xcvrPresent=True
        return self.xcvrPresent
    
    def checkModuleState(self):
        self.stopXcvrPeriodic()
        self.changePage('0x11')
        val = self.readReg('0x80')
        self.startXcvrPeriodic()
        return val
    
    def stopXcvrPeriodic(self):
        self.xcvrPeriodicRunning = False
        return dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  xcvr_periodic_stop", target=f"fpc{self.fpc}", timeout="1")

    def startXcvrPeriodic(self):
        self.xcvrPeriodicRunning = True
        return dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  xcvr_periodic_start", target=f"fpc{self.fpc}", timeout="1")
    
    def changePage(self, page):
        return self.writeReg('0x7f', page, page=page)

    def writeReg(self, address, value, page=None):
        if page is None:
            page = self.currentPage
        result = dev.rpc.request_pfe_execute(command=f"test picd optics write fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} address {address} value {value}", target=f"fpc{self.fpc}", timeout="1")
        if page != "":
            result = dev.rpc.request_pfe_execute(command=f"test picd optics write fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} page {page} address {address} value {value}", target=f"fpc{self.fpc}", timeout="1")
        if address == "0x7f":
            self.currentPage = page
        return result.text

    def readReg(self, address, page=None):
        if page is None:
            page = self.currentPage
        val=dev.rpc.request_pfe_execute(command=f"test picd optics read fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} address {address}", target=f"fpc{self.fpc}", timeout="1")
        match = re.findall(r'Val: 0x([0-9,a-f]+)',val.text)
        if not match and page != "":
            val=dev.rpc.request_pfe_execute(command=f"test picd optics read fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} page {page} address {address}", target=f"fpc{self.fpc}", timeout="1")
            match = re.findall(r'Val: 0x([0-9,a-f]+)',val.text)
        if not match:
            sys.exit(f"Failed to read address {address} (page {page}): {val.text.strip()}")
        val = match[0]
        if len(val) == 1:
            return '0' + val
        else:
            return val
        
    def checkModuleInfo(self):
        picDetail=dev.rpc.get_pic_detail(normalize=True,fpc_slot=self.fpc,pic_slot=self.pic)
        jpn=picDetail.find(f'fpc/pic-detail/port-information/port/[port-number="{self.port}"]/sfp-vendor-pno').text
        vendor = picDetail.find(f'fpc/pic-detail/port-information/port/[port-number="{self.port}"]/sfp-vendor-name').text
        return jpn,vendor
    
    def dp_deinit(self):
        self.changePage('0x10')
        self.writeReg('0x82','0xff')
        self.writeReg('0x80','0xff')

        self.changePage('0x11')
        if self.readReg('0x80') == "11":
            print("DP Deactivated!")
        else:
            self.dp_deinit()

    def dp_init(self):
        self.changePage('0x10')
        self.writeReg('0x80','0x00')
        self.writeReg('0x82','0x00')

        if self.readReg('0x80') == '00':
            print("DP Reactivated!")
        else:
            self.dp_init()

    def softOIR(self):
        dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  oir_enable", target=f"fpc{self.fpc}", timeout="1")
        dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  remove", target=f"fpc{self.fpc}", timeout="1")
        sleep(3)
        dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  insert", target=f"fpc{self.fpc}", timeout="1")
        dev.rpc.request_pfe_execute(command=f"test picd optics fpc_slot {self.fpc} pic_slot {self.pic} port {self.port} cmd  oir_disable", target=f"fpc{self.fpc}", timeout="1")
    
    def dp_applyInitLane(self):
        self.changePage('0x10')
        self.writeReg('143','0xff')

    def intStatus(self):
        intInfo=dev.rpc.get_interface_information(interface_name=self.interface,normalize=True)
        self.operStatus=intInfo.find(f'physical-interface/oper-status').text
        deviceFlags=intInfo.findall(f'physical-interface/if-device-flags/')
        for deviceFlag in deviceFlags: 
            if 'ifdf-xcvr-error' in deviceFlag.tag:
                self.xcvr_error = True
            else:
                self.xcvr_error = False
        return self.operStatus, self.xcvr_error
    
class changeCDC():
    def __init__(self, jpn):
        if jpn == "JUNIPER-1T" and (xcvr.jpn == '740-131168' or xcvr.jpn == '740-131169'):
            self.jpn = jpn
        elif jpn == "JUNIPER-2E" and xcvr.jpn == '740-157138':
            self.jpn = jpn
        elif jpn == "JUNIPER-1A" and (xcvr.jpn == '740-151745' or xcvr.jpn == '740-179331'):
            self.jpn = jpn
        else:
            sys.exit("Module not supported")

    def signedHex_to_dec(self, signedHex):
        return  int((1 << 32) - int(signedHex,16))
    
    def dec_to_signedHex(self, dec):
        return hex((1 << 32) - int(dec))
    
    def unsignedHex_to_dec(self, unsignedHex):
        return int(unsignedHex,16)
    
    def dec_to_unsignedHex(self, dec, numberofBytes):
        return format(int(dec),f'#0{numberofBytes*2+2}x')
    
    def readCurrentCDCSettings(self, page, startAddress, numberofBytes):
        xcvr.changePage(page)
        currentCDChex=""
        for x in range(numberofBytes):
            currentCDChex=currentCDChex + xcvr.readReg(startAddress + x)
        return currentCDChex
    
    def changeCurrentCDCsettings(self, page, startAddress, hexCDC):
        xcvr.changePage(page)
        numberofBytes=int((len(hexCDC)-2)/2)
        for x in range(numberofBytes):
            xcvr.writeReg(startAddress + x, f"0x{hexCDC[2*x+2:2*x+4]}")

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
    
    def run(self):
        startTime = datetime.datetime.now().timestamp()
        moduleState=xcvr.checkModuleState()

        while  moduleState != '44' and moduleState != '55'and moduleState != '77':
            print(f'Waiting for DP to be activated, currently {moduleState[0]}. Time elapsed: {round(datetime.datetime.now().timestamp() - startTime)} seconds')
            moduleState=xcvr.checkModuleState()

        print(f"DP Activated ({moduleState[0]})! Deactivating DP.")
        xcvr.stopXcvrPeriodic()
        xcvr.dp_deinit()
        
        if self.jpn == 'JUNIPER-1T':
            self.QDD_400G_ZR_M_HP()
        elif self.jpn == 'JUNIPER-2E':
            self.JCO400_QDD_ZR_M()
        elif self.jpn == 'JUNIPER-1A':
            self.JCO400_QDD_ZR_M_HP()

        self.wrapUp(xcvr.currentCDC)

    def wrapUp(self, currentCDCdec):
        xcvr.dp_init()
        xcvr.startXcvrPeriodic()
        if int(currentCDCdec) == desiredCDCdec:
            print("Max CDC configuration succeeded! Please wait for link-up. ~ 2 mins")
        else:
            sys.exit("Max CDC configuration Failed. Please Try Again")

        intStatus, moduleFault = xcvr.intStatus()
        startTime = datetime.datetime.now().timestamp()
        timeout=300
        sleepTime=5
        print(f"Waiting for Link Up. Timeout is {timeout} seconds")
        while intStatus.lower() == "down":
            if moduleFault:
                response = input("Module is in Fault State. Do you want to perform soft OIR and try again? (y/n): ")
                if response.lower() == 'y':
                    xcvr.softOIR()
                    self.run()
                else:
                    sys.exit("Module Fault!")
            
            print(f"Waiting for Link Up.  Time elapsed: {round(datetime.datetime.now().timestamp() - startTime)} seconds. ")   
            intStatus, moduleFault = xcvr.intStatus() 
            sleep(sleepTime)

            if datetime.datetime.now().timestamp()  > startTime + timeout:
                sys.exit("Timeout!, Please try again.")

        if intStatus.lower() == 'up':
            print("Link Up!")

    def QDD_400G_ZR_M_HP(self):
        global xcvr

        print("Reading Current Max CDC Setting")
        currentCDChex=self.readCurrentCDCSettings('0xBA',188,4)
        xcvr.currentCDC=self.signedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is {xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {desiredCDCdec} ps/nm.")
        desiredCDChex=self.dec_to_signedHex(desiredCDCdec)
        self.changeCurrentCDCsettings('0xB8',200,desiredCDChex)

        print("Done! Verifying if accepted by the module.")
        currentCDChex=self.readCurrentCDCSettings('0xBA',188,4)
        xcvr.currentCDC=self.signedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is now {xcvr.currentCDC} ps/nm.")

    def JCO400_QDD_ZR_M(self):
        global desiredCDCdec
        global xcvr

        print("Reading Current Max CDC Setting")
        xcvr.changePage('0x31')
        if xcvr.readReg('248') == "01":
            currentCDChex=self.readCurrentCDCSettings('0x31',249,2)
            currentCDCmultiplier = self.unsignedHex_to_dec(xcvr.readReg('251'))
        else:
            currentCDChex=self.readCurrentCDCSettings('0x31',252,2)
            currentCDCmultiplier = 10
        xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex) * currentCDCmultiplier
        print(f"Current Max CDC Setting is {xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {desiredCDCdec} ps/nm.")
        multiplier = 0
        if desiredCDCdec > 65535:
            multiplier=self.JUNIPER_2E_multiplierChecker(desiredCDCdec)
            if multiplier == 0:
                print("Desired Max CDC Setting is a prime number. Adding 1.")
                desiredCDCdec+=1
                multiplier=self.JUNIPER_2E_multiplierChecker(desiredCDCdec)
                print(f"Target Max CDC Setting is now {desiredCDCdec}")
        else:
            multiplier = 1
        xcvr.changePage('0x31')
        xcvr.writeReg('248','0x01')
        desiredCDChex=self.dec_to_unsignedHex(desiredCDCdec//multiplier,2)
        self.changeCurrentCDCsettings('0x31',249,desiredCDChex)
        xcvr.writeReg('251',self.dec_to_unsignedHex(multiplier,1))
        xcvr.dp_applyInitLane()

        print("Done! Verifying if accepted by the module.")
        xcvr.changePage('0x31')
        if xcvr.readReg('248') == "01":
            currentCDChex=self.readCurrentCDCSettings('0x31',249,2)
            currentCDCmultiplier = self.unsignedHex_to_dec(xcvr.readReg('251'))
        else:
            currentCDChex=self.readCurrentCDCSettings('0x31',252,2)
            currentCDCmultiplier = 10
        xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex) * currentCDCmultiplier
        print(f"Current Max CDC Setting is now {xcvr.currentCDC} ps/nm.")

    def JCO400_QDD_ZR_M_HP(self):
        global xcvr

        print("Reading Current Max CDC Setting")
        currentCDChex=self.readCurrentCDCSettings('0x1E',0x80,4)
        xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is {xcvr.currentCDC} ps/nm.")

        print(f"Changing CDC Setting to {desiredCDCdec} ps/nm.")
        xcvr.changePage('0x1E')
        xcvr.writeReg('0x84','0x01')
        desiredCDChex=self.dec_to_unsignedHex(desiredCDCdec,4)
        self.changeCurrentCDCsettings('0x1E',0x80,desiredCDChex)
        xcvr.dp_applyInitLane()

        print("Done! Verifying if accepted by the module.")
        currentCDChex=self.readCurrentCDCSettings('0x1E',0x80,4)
        xcvr.currentCDC=self.unsignedHex_to_dec(currentCDChex)
        print(f"Current Max CDC Setting is now {xcvr.currentCDC} ps/nm.")

if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(description="Change MAX CDC")
    arg_parser.add_argument(('--interface'),required=True, help="Interface Name")
    arg_parser.add_argument(('--max_cdc'),required=True, help="Desired Max CDC in ps/nm")
    args = arg_parser.parse_args()
    
    try:
        dev = Device().open()
    except ConnectError as err:
        print ("Cannot connect to device: {0}".format(err))
        sys.exit(1)
    except Exception as err:
        print (err)
        sys.exit(1)

    if 'not found' in dev.rpc.get_interface_information({'format':'text'},interface_name=args.interface).text.lower():
        if 'not found' in dev.rpc.get_interface_information({'format':'text'},interface_name=f"{args.interface}:0").text.lower():
            sys.exit("Interface Name not found") 
        else:
            args.interface=f"{args.interface}:0"

    usage = f"""
This script changes the maximum Chromatic Dispersion Compensation settings.
The script modifies the module's registers via CMIS to change the CDC.
The script is now going to change the maximum Chromatic Dispersion Compensation setting of {args.interface} to {args.max_cdc} ps/nm.
    """
    print(usage)

    xcvr=Xcvr(args.interface)

    print(f'JPN is {xcvr.jpn}')
    print(f'Vendor is {xcvr.vendor}')
    intStatus, moduleFault = xcvr.intStatus()

    if moduleFault:
        response = input("Module is in Fault State. Do you want to perform soft OIR before trying? (y/n): ")
        if response.lower() == 'y':
                xcvr.softOIR()
        else:
            sys.exit("Module Fault!")
    
    desiredCDCdec=int(args.max_cdc)
    xcvr_configurator=changeCDC(xcvr.vendor.upper()[:-1])
    xcvr_configurator.run()