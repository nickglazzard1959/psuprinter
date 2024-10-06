#! /usr/bin/env python3
# netprinter.py - Emulate a printer for NOS PSU with Kevin's DtCYBER version.
# Nick Glazzard 2021, 2022, 2024.
import socket
import errno
import select
import time
import re
import sys
import os
import subprocess
import argparse
import unicodedata
import re

def remove_control_characters(s):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    result = ansi_escape.sub('', s)
    return "".join(ch for ch in result if unicodedata.category(ch)[0]!="C")

def _bytestostr( ccharpin ):
    """
    Convert an array of 8 bit bytes, such as may be returned from C code
    using c_char_p arguments, to a string.
    """
    if ccharpin is None:
        return None
    else:
        return ccharpin.decode('utf-8')

def ex_fix_fld(line, colrange):
    """
    Extract a range of columns (inclusive) from line. Clean up the extracted text.
    """
    inc = max(0,colrange[0])
    outc = min(len(line)-1,colrange[1])+1
    text = line[inc:outc]
    text = text.strip(' .,')
    text = text.replace('/','_')
    text = text.replace('.','_')
    return text    

class psu_printer( object ):
    """
    Connect to NOS Printer Support Utility (PSU) and act as a
    printer.
    """

    def __init__(self, outdir, hostname, port=2552, debug=False):
        """
        Create a printer, connect to PSU on hostname:port.
        """
        super(psu_printer,self).__init__()

        # Current state codes.
        self.UNCONNECTED = 1
        self.CONNECTED = 2
        self.LOGGING_IN = 3
        self.LOGGED_IN = 4
        self.BANNER_PARSED = 5
        self.FILE_DONE = 6

        # Primary options.
        self.debug = debug
        self.outdir = outdir
        self.hostname = hostname
        self.port = port

        # Secondary PDF options.
        self.landscape = True
        self.greenbar = False
        self.economy = False

        # Initial state.
        self.old_state = 0
        self.state = self.UNCONNECTED
        self.clear_parsed_items()

    def process_print_jobs(self):
        """
        Loop, maintaining and responding to state.
        Parse the PSU output, creating files in outdir.
        """
        while True:
            self.print_state()

            # If not connected, connect.
            if self.state == self.UNCONNECTED:
                self.text = ''
                
                # Connect to PSU.
                while self.state == self.UNCONNECTED:
                    self.psu = self.connect_to_psu()
                    if self.psu is None:
                        time.sleep(5)
                    else:
                        self.state = self.CONNECTED
                        
            elif self.state == self.CONNECTED:
                # On connection, process PSU output. Read all available data.

                while True:
                    self.print_state()
                    bytedata = self.psu.recv(2048)

                    # If we didn't get any bytes, the connection has closed.
                    if len(bytedata) == 0:
                        self.state == self.UNCONNECTED
                        time.sleep(5)
                        break

                    # Process the received data according to the current state.
                    # Each "state processor" should eat as much of the input data as possible.
                    # To do that, have each one call the processor for the next state before returning.
                    else:
                        stringdata = _bytestostr(bytedata)
                        
                        # If CONNECTED, locate marker of login, transition to LOGGING_IN.
                        if self.state == self.CONNECTED:
                            self.find_login_marker(stringdata)

                        # If LOGGING_IN, locate end of login page, transition to LOGGED_IN.
                        elif self.state == self.LOGGING_IN:
                            self.find_login_end(stringdata)

                        # If LOGGED_IN, parse the banner page, open output file, transition to BANNER_PARSED.
                        elif self.state == self.LOGGED_IN:
                            self.banner_parse(stringdata)

                        # If BANNER_PARSED, locate end of user output, transition to FILE_DONE.
                        elif self.state == self.BANNER_PARSED:
                            self.process_pages(stringdata)         

                        # If FILE_DONE, close the output file, transition to LOGGED_IN.
                        elif self.state == self.FILE_DONE:
                            self.close_output_file()
                
    def connect_to_psu(self):
        """
        Open a connection to PSU on hostname.
        Return None if fails, else socket.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.hostname, self.port))
            return sock
        except Exception as e:
            print('connect_to_psu(): failed, reason:', e)
            return None

    def print_state(self):
        """
        Debug: display state name.
        """
        statedict = {self.UNCONNECTED   : 'UNCONNECTED',
                     self.CONNECTED     : 'CONNECTED',
                     self.LOGGING_IN    : 'LOGGING_IN',
                     self.LOGGED_IN     : 'LOGGED_IN',
                     self.BANNER_PARSED : 'BANNER_PARSED',
                     self.FILE_DONE     : 'FILE_DONE'}
        if self.debug and (self.state != self.old_state):
            print('New state:',statedict[self.state])
            self.old_state = self.state

    def clear_parsed_items(self):
        """
        Set items parsed from banner pages to empty.
        """
        self.date = ''
        self.time = ''
        self.ujn = ''
        self.jsn = ''
        self.user = ''
        self.file_name = ''
        self.path_name = ''
        self.parsed_items = 0
        self.banner_buffer = ''
        self.fout = None

    def close_output_file(self):
        """
        Close any open output file. Clear parsed items.
        """
        if self.fout is not None:
            self.fout.close()
            self.make_pdf()
            print('INFO: output completed.')
        self.clear_parsed_items()
        self.state = self.LOGGED_IN

    def make_pdf(self):
        """
        Convert the output file to PDF format.
        """
        outpdfdir = os.path.join(self.outdir, 'PDF')
        if not os.access(outpdfdir, os.F_OK):
            try:
                os.makedirs(outpdfdir)
            except Exception as e:
                print('Cannot create:', outpdfdir, 'Reason:', e)
                return False
        filen,ext = os.path.splitext(self.file_name)
        outpdffile = filen + '.pdf'
        outpdfpath = os.path.join(outpdfdir, outpdffile)
        topdfpgm = os.path.join(os.path.dirname(__file__),'text2pdf.py')
        cmd = [ 'python',
                topdfpgm,             # Conversion program file name.
                self.path_name,       # Input ASCII text file name.
                '-c', '137',          # Characters per line before wrapping.
                '-T', '137',          # Characters per line before truncation.
                '-l', '67',           # Lines per page.
                '-F',                 # Use ^L to signal a page break.
                '-s', '8',            # Font size (points).
                '-v', '8',            # Line spacing.
                '-q',                 # Quiet mode.
                '-A', 'CDC Printer Support Utility',
                '-S', 'CDC NOS 2 Output',
                '-f', 'Courier-Bold', # Font to use. Non-bold looks a bit "thin".
                '-o', outpdfpath]     # Output PDF file name.
        if self.economy:
            cmd.append( '-v' )        # In economy mode, space lines by 6 units.
            cmd.append( '6' )
            cmd.append( '-l' )        # ... change page length to match.
            cmd.append( '89' )
        if self.landscape:
            cmd.append( '-L' )        # Landscape mode.
        else:
            cmd.append( '-l')         # Portrait mode.
            if self.economy:
                cmd.append( '117' )   # ... change to 117 lines per page in economy mode.
            else:
                cmd.append( '88' )    # ... change to 88 lines per page in normal mode.
            cmd.append( '-T' )        # ... truncate after 102 chars without wrapping.
            cmd.append( '102' )       # ... still use -c characters for line movement logic.
        if self.greenbar:
            cmd.append( '-G' )        # Greenbar paper mode.
        try:
            retstring = subprocess.check_output(cmd, universal_newlines=True)
            print('INFO: created PDF output file:',outpdfpath)
            print(retstring)
            return True
        except Exception as e:
            print('lp2pdf run failed. Reason:', e)
            print(' cmd was:',cmd)
            return False
        
        return True

    def find_login_marker(self, stringdata):
        """
        Search self.text for an identifying part of the PSU login sequence.
        """
        self.text += stringdata
        match = re.search('[\f\r\n]', self.text)
        while match:
            line = self.text[0:match.end()]
            printline = remove_control_characters(line.strip())
            if len(printline.strip()) > 0:
                print(printline)
            self.text = self.text[match.end():]
            if line.startswith('PRINTER SUPPORT UTILITY'):
                self.state = self.LOGGING_IN
                self.print_state()
                self.find_login_end('')
                return
            match = re.search('[\f\r\n]', self.text)

    def find_login_end(self, stringdata):
        """
        Search self.text for the end of the PSU login sequence (next form feed).
        """
        self.text += stringdata
        match = re.search('[\f]', self.text)
        if match:
            self.state = self.LOGGED_IN
            self.print_state()
            self.text = self.text[match.end():]
            self.banner_parse('')
            return

    def trim_leading_ff(self, banner_buffer):
        """
        Given the contents of a buffer containing (part of) the banner page,
        if there is a form feed before the banner itself, remove the start up to
        and including the FF. This is probably a side effect of the same problem that
        requires match_process_pages().
        """
        match_ff = re.search('[\f]', banner_buffer)
        match_printing = re.search('[^\f\r\n]', banner_buffer)
        if match_ff and match_printing:
            ff_index = match_ff.end()
            printing_index = match_printing.end()
            if ff_index < printing_index:
                return banner_buffer[ff_index+1:]
        return banner_buffer
        
    def banner_parse(self, stringdata):
        """
        Parse the banner page, concoct a file name and open an output file.
        """
        self.text += stringdata
        match = re.search('[\f\r\n]', self.text)
        while match:
            iend = match.end()
            line = self.text[0:iend]
            self.text = self.text[iend:]

            # Parse the banner page, finding data to make a file name from.
            if len(line) > 20:
                sigline = line[19:]
                if sigline.startswith('OPERATING SYSTEM =  NOS 2.8.7 871/871.'):
                    self.date = ex_fix_fld(line, (80,88))
                    self.time = ex_fix_fld(line, (90,98))
                    self.parsed_items += 2
                elif sigline.startswith('UJN          ='):
                    self.ujn = ex_fix_fld(line, (35,42))
                    self.parsed_items += 1
                elif sigline.startswith('CREATING JSN ='):
                    self.jsn = ex_fix_fld(line, (35,42))
                    self.user = ex_fix_fld(line, (59,66))
                    if self.user == '':
                        self.user = ex_fix_fld(line, (89,96))
                    self.parsed_items += 2

            # If a file is not yet open, accumulate the banner page lines.
            self.banner_buffer += line

            # If all required information has been found, try to create an output file.
            if self.parsed_items == 5:
                self.file_name = self.user+'.'+self.ujn+'.'+self.jsn+'.'+self.date+'.'+self.time+'.txt'
                self.path_name = os.path.join(self.outdir, self.file_name)
                self.fout = open(self.path_name, 'w')
                if self.fout is not None:
                    print('\nINFO: created output file:',self.path_name,flush=True)
                else:
                    print('ERROR: failed to create output file:',self.path_name,flush=True)

                # If pre-open banner page lines have been accumulated, write them out first.
                if len(self.banner_buffer) > 0:
                    if self.fout is not None:
                        self.fout.write(self.trim_leading_ff(self.banner_buffer))
                        self.fout.flush()
                    self.banner_buffer = ''

                # Reset for next banner page and start reading/writing all remaining input lines.
                self.parsed_items = 0
                self.state = self.BANNER_PARSED
                self.print_state()
                self.process_pages('')
                return
            match = re.search('[\f\r\n]', self.text)

    def match_process_pages(self):
        """
        Treat any of FF, CR or NL as usual as a line terminator, OR ESC \
        It seems as if the CR/LF after this is not output until the *next* job ...
        or something like that.
        """
        match = re.search('[\f\r\n]', self.text)
        if match:
            return match
        match = re.search('\x1b\\\\', self.text)
        return match

    def process_pages(self, stringdata):
        """
        Process output pages, writing output lines until end of file marker is found.
        """
        self.text += stringdata
        match = self.match_process_pages()
        while match:
            line = self.text[0:match.end()]
            self.text = self.text[match.end():]
            if (line.find('** END OF LISTING **') >= 0) and (line.find('UCLP') >= 0):
                self.state = self.FILE_DONE
                self.print_state()
                self.close_output_file()
                return
            else:
                if self.fout is not None:
                    self.fout.write(line)
                    self.fout.flush()
            match = self.match_process_pages()

def main_core():
    print("\nPSUprinter: CDC PSU client")
    print(  "==========================")

    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="Host to connect to.")
    parser.add_argument("outdir", help="Output directory.")
    parser.add_argument("--debug", "-d", help="Print debug information.", action='store_true')
    parser.add_argument("--port", help="TCP port for PSU (def:2552).")
    parser.add_argument("--portrait", help="Portrait mode printing (def:landscape).", action='store_true')
    parser.add_argument("--greenbar", help="Greenbar paper background (def:plain).", action='store_true')
    parser.add_argument("--economy", help="Reduce space between lines to save paper.", action='store_true')
    
    args = parser.parse_args()

    if args.port is None:
        port = 2552
    else:
        port = args.port

    if not os.access(args.outdir, os.F_OK):
        try:
            os.makedirs(args.outdir)
        except Exception as e:
            print('Cannot create:', args.outdir, 'Reason:', e)
            sys.exit(1)
            
    printer = psu_printer(args.outdir, args.host, debug=args.debug, port=port)

    printer.landscape = not args.portrait
    printer.greenbar = args.greenbar
    printer.economy = args.economy
    
    printer.process_print_jobs()

def main():
    try:
        main_core()
    except KeyboardInterrupt:
        print('\nExiting PSUprinter.')
        sys.exit(1)    
            
if __name__ == "__main__":
    main()
