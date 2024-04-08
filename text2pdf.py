#! /usr/bin/env python3
"""
 pyText2Pdf - Python script to convert plain text files into Adobe
 Acrobat PDF files with support for arbitrary page breaks etc.

 Version 2.0

 Author: Anand B Pillai <abpillai at gmail dot com>
 Hacked by Nick Glazzard to add a cosmetic green bar paper background
 and Python 3 compatibility. Also to get over printing to work (tricky).
 Note: this overstrike does not support ^H. Only "Fortran style" column 1
 format effectors converted to carriage returns without line feeds.
    
"""

# Derived from http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/189858

import sys, os
import string
import time
import optparse
import re

LF_EXTRA=0
LINE_END='\015'
# form feed character (^L)
FF=chr(12)

ENCODING_STR = """\
/Encoding <<
/Differences [ 0 /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /space /exclam
/quotedbl /numbersign /dollar /percent /ampersand
/quoteright /parenleft /parenright /asterisk /plus /comma
/hyphen /period /slash /zero /one /two /three /four /five
/six /seven /eight /nine /colon /semicolon /less /equal
/greater /question /at /A /B /C /D /E /F /G /H /I /J /K /L
/M /N /O /P /Q /R /S /T /U /V /W /X /Y /Z /bracketleft
/backslash /bracketright /asciicircum /underscore
/quoteleft /a /b /c /d /e /f /g /h /i /j /k /l /m /n /o /p
/q /r /s /t /u /v /w /x /y /z /braceleft /bar /braceright
/asciitilde /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/.notdef /.notdef /.notdef /.notdef /.notdef /.notdef
/dotlessi /grave /acute /circumflex /tilde /macron /breve
/dotaccent /dieresis /.notdef /ring /cedilla /.notdef
/hungarumlaut /ogonek /caron /space /exclamdown /cent
/sterling /currency /yen /brokenbar /section /dieresis
/copyright /ordfeminine /guillemotleft /logicalnot /hyphen
/registered /macron /degree /plusminus /twosuperior
/threesuperior /acute /mu /paragraph /periodcentered
/cedilla /onesuperior /ordmasculine /guillemotright
/onequarter /onehalf /threequarters /questiondown /Agrave
/Aacute /Acircumflex /Atilde /Adieresis /Aring /AE
/Ccedilla /Egrave /Eacute /Ecircumflex /Edieresis /Igrave
/Iacute /Icircumflex /Idieresis /Eth /Ntilde /Ograve
/Oacute /Ocircumflex /Otilde /Odieresis /multiply /Oslash
/Ugrave /Uacute /Ucircumflex /Udieresis /Yacute /Thorn
/germandbls /agrave /aacute /acircumflex /atilde /adieresis
/aring /ae /ccedilla /egrave /eacute /ecircumflex
/edieresis /igrave /iacute /icircumflex /idieresis /eth
/ntilde /ograve /oacute /ocircumflex /otilde /odieresis
/divide /oslash /ugrave /uacute /ucircumflex /udieresis
/yacute /thorn /ydieresis ]
>>
"""

INTRO="""\
%prog [options] filename

PyText2Pdf  makes a 7-bit clean PDF file from any input file.

It reads from a named file, and writes the PDF file to a file specified by
the user, otherwise to a file with '.pdf' appended to the input file.

Author: Anand B Pillai.
        Hacked by Nick Glazzard to add a cosmetic green bar paper background
        and Python 3 compatibility.  Also to get over printing to work (tricky).
"""

def _strtobytes( py3string ):
    """
    Convert a Python3 string to UTF-8 bytes to pass as c_char_p to C functions.
    For strings that should be so passed, this will result in 8 bit bytes, which
    is as required. For other (Unicode) strings ... tough luck.
    """
    if py3string is None:
        return None
    else:
        return py3string.encode('utf-8')

def _bytestostr( ccharpin ):
    """
    Convert an array of 8 bit bytes, such as may be returned from C code
    using c_char_p arguments, to a string.
    """
    if ccharpin is None:
        return None
    else:
        return ccharpin.decode('utf-8')

class PyText2Pdf(object):
    """
    Text2pdf converter in pure Python.
    """
    
    def __init__(self):
        # version number
        self._version="1.3"
        # iso encoding flag
        self._IsoEnc = False
        # formfeeds flag
        self._doFFs = False
        self._progname = "PyText2Pdf"
        self._appname = " ".join((self._progname,str(self._version)))
        # default font
        self._font = "/Courier"
        # default font size
        self._ptSize = 10
        # default vert space
        self._vertSpace = 12
        self._lines = 0
        # number of characters in a row
        self._cols = 80
        self._columns = 1
        # page ht
        self._pageHt = 792
        # page wd
        self._pageWd = 612
        # input file 
        self._ifile = ""
        # output file 
        self._ofile = ""
        # default tab width
        self._tab = 4
        # input file descriptor
        self._ifs = None
        # output file descriptor
        self._ofs = None
        # landscape flag
        self._landscape = False
        # greenbar flag
        self._greenbar = False
        # quiet flag
        self._quiet = False
        # Subject
        self._subject = ''
        # Author
        self._author = ''
        # Keywords
        self._keywords = []
        
        # Marker objects.
        # Attempts to turn off "text knock out" and turn on overprinting
        # do not seem to be necessary to get overprinting to work after all.
        if False:
            self._curobj = 6
            self._locations = [0,0,0,0,0,0,0]
        else:
            self._curobj = 5
            self._locations = [0,0,0,0,0,0]
        self._pageObs = [0]
        self._pageNo = 0

        # file position marker
        self._fpos = 0

    def parse_args(self):   
        """
        Callback function called by argument parser.
        Helps to remove duplicate code.
        """
        if len(sys.argv)<2:
            sys.argv.append('-h')
            
        parser = optparse.OptionParser(usage=INTRO)
        parser.add_option('-o','--output',dest='outfile',help='Direct output to file OUTFILE',metavar='OUTFILE')
        parser.add_option('-f','--font',dest='font',help='Use Postscript font FONT (must be in standard 14, default: Courier)',
                          default='Courier')
        parser.add_option('-I','--isolatin',dest='isolatin',help='Use ISO latin-1 encoding',default=False,action='store_true')
        parser.add_option('-s','--size',dest='fontsize',help='Use font at PTSIZE points (default=>10)',metavar='PTSIZE',default=10)
        parser.add_option('-v','--linespace',dest='linespace',help='Use line spacing LINESPACE (default 12)',metavar='LINESPACE',default=12)
        parser.add_option('-l','--lines',dest='lines',help='Lines per page (default 60, determined automatically if unspecified)',default=60, metavar=None)
        parser.add_option('-c','--chars',dest='chars',help='Maximum characters per line (default 80)',default=80,metavar=None)
        parser.add_option('-t','--tab',dest='tabspace',help='Spaces per tab character (default 4)',default=4,metavar=None)
        parser.add_option('-F','--useff',dest='formfeed',help='Use formfeed character ^L (i.e. accept formfeed characters as page breaks)',default=False,action='store_true')
        parser.add_option('-G','--greenbar',dest='greenbar',help='Add green bar background.',default=False,action='store_true')
        parser.add_option('-P','--papersize',dest='papersize',help='Set paper size (default is letter, accepted values are "A4" or "A3")')
        parser.add_option('-W','--width',dest='width',help='Independent paper width in points',metavar=None,default=612)
        parser.add_option('-H','--height',dest='height',help='Independent paper height in points',metavar=None,default=792)
        parser.add_option('-2','--twocolumns',dest='twocolumns',help='Format as two columns',metavar=None,default=False,action='store_true')
        parser.add_option('-L','--landscape',dest='landscape',help='Format in landscape mode',metavar=None,default=False,action='store_true')
        parser.add_option('-S','--subject',dest='subject',help='Optional subject for the document',metavar=None)
        parser.add_option('-A','--author',dest='author',help='Optional author for the document',metavar=None)
        parser.add_option('-K','--keywords',dest='keywords',help='Optional list of keywords for the document (separated by commas)',metavar=None)
        parser.add_option('-q','--quiet',dest='quiet',help='Do not print informational messages.',default=False,action='store_true')
        
        optlist, args = parser.parse_args()
        # print optlist.__dict__, args

        if len(args) == 0:
            sys.exit('Error: input file argument missing')
        elif len(args)>1:
            sys.exit('Error: Too many arguments')            

        self._ifile = args[0]
        
        d = optlist.__dict__
        if d.get('isolatin'): self._IsoEnc=True
        if d.get('formfeed'): self._doFFs = True
        if d.get('twocolumns'): self._columns = 2
        if d.get('landscape'): self._landscape = True
        if d.get('greenbar'): self._greenbar = True
        if d.get('quiet'): self._quiet = True

        self._font = '/' + d.get('font')
        psize = d.get('papersize')
        if psize == 'A4':
            self._pageWd = 595
            self._pageHt = 842
        elif psize == 'A3':
            self._pageWd = 842
            self._pageHt = 1190

        fsize = int(d.get('fontsize'))
        if fsize < 1: fsize = 1
        self._ptSize = fsize

        lspace = int(d.get('linespace'))
        if lspace < 1: lspace = 1
        self._vertSpace = lspace

        lines = int(d.get('lines'))
        if lines < 1: lines = 1
        self._lines = int(lines)

        chars = int(d.get('chars'))
        if chars < 4: chars = 4
        self._cols = chars

        tab = int(d.get('tabspace'))
        if tab < 1: tab = 1
        self._tab = tab

        w = int(d.get('width'))
        if w < 72: w = 72
        self._pageWd = w

        h = int(d.get('height'))
        if h < 72: h = 72
        self._pageHt = h

        # Very optional args
        author = d.get('author')
        if author: self._author = author

        subject = d.get('subject')
        if subject: self._subject = subject

        keywords = d.get('keywords')
        if keywords:
            self._keywords = keywords.split(',')

        outfile = d.get('outfile')
        if outfile: self._ofile = outfile
        
        if self._landscape and not self._quiet:
            print('Landscape option on...')
        if self._columns==2 and not self._quiet:
            print('Printing in two columns...')
        if self._doFFs and not self._quiet:
            print('Using form feed character...')
        if self._IsoEnc and not self._quiet:
            print('Using ISO Latin Encoding...')

        if not self._quiet:
            print('Using font',self._font[1:],'size =', self._ptSize)

    def writestr(self, str):
        """
        Write string to output file descriptor.
        All output operations go through this function.
        We keep the current file position also here.
        """
        # Update current file position
        self._fpos += len(str)
        for x in range(0, len(str)):
            if str[x] == '\n':
                self._fpos += LF_EXTRA
        try:
            self._ofs.write( _strtobytes(str))
        except IOError as e:
            print(e)
            return -1

        return 0
            
    def convert(self):
        """
        Perform the actual conversion.
        """
    
        if self._landscape:
            # swap page width & height
            tmp = self._pageHt
            self._pageHt = self._pageWd
            self._pageWd = tmp

        if self._lines == 0:
            self._lines = (self._pageHt - 72) / self._vertSpace
        if self._lines < 1:
            self._lines = 1

        # Open the input file in binary mode so we get to see carriage returns.
        try:
            self._ifs=open(self._ifile, 'rb')
        except IOError as e:
            print('Error: Could not open file to read --->', self._ifile)
            print('Reason:', e)
            sys.exit(3)

        if self._ofile == "":
            self._ofile = os.path.splitext(self._ifile)[0] + '.pdf'

        # Open output file in binary mode.
        try:
            self._ofs = open(self._ofile, 'wb')
        except IOError as e:
            print('Error: Could not open file to write --->', self._ofile)
            print('Reason:', e)
            sys.exit(3)

        if not self._quiet:
            print('Input file =>',self._ifile)
            print('Writing pdf file',self._ofile, '...')

        # Write header, then all pages, then trailer.
        self.writeheader()
        self.writepages()
        self.writerest()

        if not self._quiet:
            print('Wrote file', self._ofile)

        # Close files.
        self._ifs.close()
        self._ofs.close()
        return 0

    def writeheader(self):
        """
        Write the PDF header
        """
        ws = self.writestr

        title = self._ifile

        # Use PDF 1.4
        t=time.localtime()
        timestr=str(time.strftime("D:%Y%m%d%H%M%S", t))
        ws("%PDF-1.4\n")

        # Output required dictionaries.
        self._locations[1] = self._fpos
        ws("1 0 obj\n")
        ws("<<\n")

        buf = "".join(("/Creator (", self._appname, " By Anand B Pillai and others)\n"))
        ws(buf)
        buf = "".join(("/CreationDate (", timestr, ")\n"))
        ws(buf)
        buf = "".join(("/Producer (", self._appname, "(\\251 Anand B Pillai and others))\n"))
        ws(buf)
        if self._subject:
            title = self._subject
            buf = "".join(("/Subject (",self._subject,")\n"))
            ws(buf)
        if self._author:
            buf = "".join(("/Author (",self._author,")\n"))
            ws(buf)
        if self._keywords:
            buf = "".join(("/Keywords (",' '.join(self._keywords),")\n"))
            ws(buf)

        if title:
            buf = "".join(("/Title (", title, ")\n"))
            ws(buf)

        ws(">>\n")
        ws("endobj\n")
    
        self._locations[2] = self._fpos

        ws("2 0 obj\n")
        ws("<<\n")
        ws("/Type /Catalog\n")
        ws("/Pages 3 0 R\n")
        ws(">>\n")
        ws("endobj\n")
        
        self._locations[4] = self._fpos
        ws("4 0 obj\n")
        ws("<<\n")
        buf = "".join(("/BaseFont ", str(self._font), " /Encoding /WinAnsiEncoding /Name /F1 /Subtype /Type1 /Type /Font >>\n"))
        ws(buf)
    
        if self._IsoEnc:
            ws(ENCODING_STR)
            
        ws(">>\n")
        ws("endobj\n")

        # Resources object.
        self._locations[5] = self._fpos
        
        ws("5 0 obj\n")
        ws("<<\n")
        ws("  /Font << /F1 4 0 R >>\n")
        ws("  /ProcSet [ /PDF /Text ]\n")
        ws(">>\n")
        ws("endobj\n")

        # Attempts to turn off "text knock out" and turn on overprinting
        # do not seem to be necessary to get overprinting to work after all.
        if False:
            self._locations[6] = self._fpos

            ws("6 0 obj\n")
            ws("<<\n")
            ws("  /Type /ExtGState\n")
            ws("  /TK false\n")
            ws("  /OP true\n")
            ws(">>\n")
            ws("endobj\n")
    
    def startpage(self):
        """
        Start a page of data.
        """
        ws = self.writestr

        # Maintain page and object counts. Get current output file offset.
        self._pageNo += 1
        self._curobj += 1

        self._locations.append(self._fpos)
        self._locations[self._curobj]=self._fpos
    
        self._pageObs.append(self._curobj)
        self._pageObs[self._pageNo] = self._curobj

        # Output page object.
        buf = "".join((str(self._curobj), " 0 obj\n"))

        ws(buf)
        ws("<<\n")
        ws("/Type /Page\n")
        ws("/Parent 3 0 R\n")
        ws("/Resources 5 0 R\n")

        self._curobj += 1
        buf = "".join(("/Contents ", str(self._curobj), " 0 R\n"))
        ws(buf)
        ws(">>\n")
        ws("endobj\n")

        # Output stream object.
        self._locations.append(self._fpos)
        self._locations[self._curobj] = self._fpos

        buf = "".join((str(self._curobj), " 0 obj\n"))
        ws(buf)
        ws("<<\n")
        
        buf = "".join(("/Length ", str(self._curobj + 1), " 0 R\n"))
        ws(buf)
        ws(">>\n")
        ws("stream\n")
        strmPos = self._fpos

        # Transformation matrix, etc. This is for text drawing.
        ws("BT\n");
        buf = "".join(("/F1 ", str(self._ptSize), " Tf\n")) # Font size
        ws(buf)
        buf = "".join(("1 0 0 1 50 ", str(self._pageHt - 40), " Tm\n")) # Text matrix
        #buf = "".join(("1 0 0 1 50 ", str(self._pageHt - 112), " Tm\n")) # Text matrix
        ws(buf)
        buf = "".join((str(self._vertSpace), " TL\n")) # Text leading (distance vertically between lines).
        ws(buf)
    
        return strmPos

    def endpage(self, streamStart):
        """
        End a page of data.
        """
        ws = self.writestr

        # End stream.
        ws("ET\n")
        streamEnd = self._fpos
        ws("endstream\n")
        ws("endobj\n")

        # Track output file offsets for objects.
        self._curobj += 1
        self._locations.append(self._fpos)
        self._locations[self._curobj] = self._fpos

        # End page object.
        buf = "".join((str(self._curobj), " 0 obj\n"))
        ws(buf)
        buf = "".join((str(streamEnd - streamStart), '\n'))
        ws(buf)
        ws('endobj\n')

    def pdfellipse(self,x,y,xr,yr):
        """
        Draw an ellipse for greenbar tractor hole ornamentation.
        """
        ws = self.writestr
        bezmagic = 0.551784
        xtang = xr * bezmagic
        ytang = yr * bezmagic
        gbuf = "%f %f m %f %f %f %f %f %f c %f %f %f %f %f %f c %f %f %f %f %f %f c %f %f %f %f %f %f c s\n"%(x-xr,y,
                                                                 x-xr,y+ytang,
                                                                 x-xtang,y+yr,
                                                                 x,y+yr,
                                                                 
                                                                 x+xtang,y+yr,
                                                                 x+xr,y+ytang,
                                                                 x+xr,y,

                                                                 x+xr,y-ytang,
                                                                 x+xtang,y-yr,
                                                                 x, y-yr,

                                                                 x-xtang, y-yr,
                                                                 x-xr, y-ytang,
                                                                 x-xr, y )
        ws(gbuf)         
    
    def writepages(self):
        """
        Write pages as PDF
        """
        ws = self.writestr

        beginstream = 0
        lineNo, charNo = 0,0
        ch, column = 0,0
        padding,i = 0,0
        atEOF = 0
        linebuf = ''

        # Loop until at EOF.
        while not atEOF:

            # Start a page.
            beginstream = self.startpage()
            column = 1

            # Handle "green bar" ornamentation.
            if(self._greenbar):

                # Bars.
                barMargin = 30
                barLines = 3
                gbuf = '%d w 0.8 1.0 0.8 RG\n'%(barLines * 9) #self._vertSpace) # Line with width = bar height.
                ws(gbuf)
                ypos = 4 * 9 - (9/4-1)
                #ypos = (4 * self._vertSpace - (self._vertSpace/4-1)) * (9.0 / self._vertSpace)
                for gline in range(barLines,60+1): #self._lines+1):
                    if((gline%(barLines * 2))==0): # Draw a bar (i.e. a line).
                        gbuf = '%d %d m %d %d l S\n'%(barMargin,ypos,self._pageWd-barMargin,ypos)
                        ws(gbuf)
                    ypos += 9 #self._vertSpace

                # HCCC text.
                ypos += (barLines-1) * 9
                xpos = 30
                gbuf='3 w %d %d m %d %d l S\n'%(xpos,ypos,xpos,ypos+27)
                ws(gbuf)
                gbuf='%d %d m %d %d l S\n'%(xpos,ypos+13,xpos+18,ypos+13)
                ws(gbuf)
                gbuf='%d %d m %d %d l S\n'%(xpos+18,ypos,xpos+18,ypos+27)
                ws(gbuf)
                for hchar in range(1,4):
                    xpos += 26
                    gbuf='%d %d m %d %d l S\n'%(xpos,ypos,xpos,ypos+27)
                    ws(gbuf)
                    gbuf='%d %d m %d %d l S\n'%(xpos,ypos+1,xpos+18,ypos+1)
                    ws(gbuf)
                    gbuf='%d %d m %d %d l S\n'%(xpos,ypos+26,xpos+18,ypos+26)
                    ws(gbuf)

                # Tractor holes.
                tractMargin = 15
                gbuf = '%d w 0.3 0.3 0.3 RG\n'%(9) #(self._vertSpace)
                ws(gbuf)
                ypos = 4 * 9 - (9/4-1)
                #ypos = 4 * self._vertSpace - (self._vertSpace/4-1)
                #ypos = (4 * self._vertSpace - (self._vertSpace/4-1)) * (9.0 / self._vertSpace)
                for gline in range(0,60+2): #self._lines+2):
                    if((gline%4)==0):
                        self.pdfellipse(tractMargin,ypos,1,1)
                        self.pdfellipse(self._pageWd-tractMargin,ypos,1,1)
                    ypos += 9 #self._vertSpace

            # Loop over print columns of page (1 or 2).
            while column <= self._columns:
                column += 1
                atFF = 0
                atBOP = 0
                lineNo = 0
                # Special flag for regexp page break
                pagebreak = False

                # Loop over lines of page or print column.
                while lineNo < self._lines and not atFF and not atEOF and not pagebreak:
                    
                    # Start new output line.
                    linebuf = ''
                    lineNo += 1
                    charNo = 0
                    ch = ''

                    # Loop over characters of line.
                    while charNo < self._cols:
                        charNo += 1
                        ch = _bytestostr(self._ifs.read(1))

                        # Break while loop if \n or (FF and doFFs) or ch is empty (EOF)
                        breakcond = (ch == '\n') or (ch==FF and self._doFFs) or (ch == '')
                        if breakcond:
                            break

                        # Output printing character.
                        if ord(ch) >= 32 and ord(ch) <= 127:
                            if ch == '(' or ch == ')' or ch == '\\':
                                linebuf += "\\"
                            linebuf += ch
                            
                        else:
                            # Deal with some format effectors and non-printing characters.
                            if ord(ch) == 9:  # tab
                                padding =self._tab - ((charNo - 1) % self._tab)
                                for i in range(padding):
                                    linebuf += " "
                                charNo += (padding -1)
                            elif ord(ch) == 13: # CR
                                charNo = 0
                                linebuf += ch
                            else:
                                if ch != FF:
                                    # write \xxx form for dodgy character
                                    buf = "".join(('\\', ch))
                                    linebuf += buf
                                else:
                                    # dont print anything for a FF
                                    charNo -= 1

                    # End of line. 
                    # Write the accumulated output string as one or more lines.
                    # This would be trivial, apart from getting overstrike to work.
                    cr_pending = False
                    ws("(")
                    len_linebuf = len(linebuf)
                    for i in range(len_linebuf):
                        ach = linebuf[i]
                        # If CR, check if it is at the end of the line or not.
                        # If it is at the end, ignore it.
                        if ach == '\r':
                            if i < (len_linebuf-1):
                                # CR not at end of line.
                                # If cr_pending already, output line without moving to next line.
                                if cr_pending:
                                    ws(") Tj\n")
                                # Otherwise, move to next line and output line that ends in CR.
                                else:
                                    ws(")'\n")
                                # Go to start of this line, open a new output string. Set cr_pending.
                                ws("0 0 Td (")
                                cr_pending = True
                                
                        # Any other character, write to the output string.
                        else:
                            ws(ach)

                    # End of the accumulated line.
                    # If CR pending, write without going to a new line. Reset cr_pending.
                    if cr_pending:
                        ws(") Tj\n")
                        cr_pending = False

                    # Otherwise, go to a new line and write the string.
                    else:
                        ws(")'\n")

                    # Reset the character accumulation buffer.
                    linebuf = ''

                    # Check end of page conditions.
                    if ch == FF:
                        atFF = 1   # Because of FF
                        
                    if lineNo == self._lines:
                        atBOP = 1  # Because line count reached.

                    # Start of new page because line count was reached.
                    # Read another character and check for end of file of FF.
                    # Not sure about Pillai's logic here. But it seems to work.
                    if atBOP:
                        pos = 0
                        ch = _bytestostr(self._ifs.read(1))
                        pos = self._ifs.tell()
                        if ch == FF:
                            ch = _bytestostr(self._ifs.read(1))
                            pos = self._ifs.tell()

                        if ch == '':
                            atEOF = 1
                        else:
                            # push position back by one char
                            self._ifs.seek(pos-1)

                    # Start of new page because of FF.
                    elif atFF:
                        ch = _bytestostr(self._ifs.read(1))
                        pos = self._ifs.tell()
                        
                        if ch == '':
                            atEOF = 1
                        else:
                            self._ifs.seek(pos-1)

                # Move to second column of print. Or not.
                if column < self._columns:
                    buf = "".join(("1 0 0 1 ",
                                   str((self._pageWd/2 + 25)),
                                   " ",
                                   str(self._pageHt - 40),
                                   " Tm\n"))
                    ws(buf)

            # End a page.
            self.endpage(beginstream)

    def writerest(self):
        """
        Finish the file
        """
        ws = self.writestr
        self._locations[3] = self._fpos

        # Page location dictionary.
        ws("3 0 obj\n")
        ws("<<\n")
        ws("/Type /Pages\n")
        buf = "".join(("/Count ", str(self._pageNo), "\n"))
        ws(buf)
        buf = "".join(("/MediaBox [ 0 0 ", str(self._pageWd), " ", str(self._pageHt), " ]\n"))
        ws(buf)
        ws("/Kids [ ")
    
        for i in range(1, self._pageNo+1):
            buf = "".join((str(self._pageObs[i]), " 0 R "))
            ws(buf)

        ws("]\n")
        ws(">>\n")
        ws("endobj\n")

        # Cross references.
        xref = self._fpos
        ws("xref\n")
        buf = "".join(("0 ", str((self._curobj) + 1), "\n"))
        ws(buf)
        buf = "".join(("0000000000 65535 f ", str(LINE_END)))
        ws(buf)

        for i in range(1, self._curobj + 1):
            val = self._locations[i]
            buf = "".join(( str(val).zfill(10), " 00000 n ", str(LINE_END) ))
            ws(buf)

        # Trailer.
        ws("trailer\n")
        ws("<<\n")
        buf = "".join(("/Size ", str(self._curobj + 1), "\n"))
        ws(buf)
        ws("/Root 2 0 R\n")
        ws("/Info 1 0 R\n")
        ws(">>\n")
        
        ws("startxref\n")
        buf = "".join((str(xref), "\n"))
        ws(buf)
        ws("%%EOF\n")
        

def main():
    pdfclass = PyText2Pdf()
    pdfclass.parse_args()
    pdfclass.convert()

if __name__ == "__main__":
    main()
