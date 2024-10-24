# psuprinter

## Purpose
Emulates a printer for the CDC Printer Support Utility (PSU) on NOS 2 running on DtCyber.
PSU lets you print text documents from NOS "remotely". For example, you can log on to
NOS (running via DtCyber on computer A on your LAN) from a terminal emulator running on
computer B (on the same LAN) and "print" documents on computer B directly. By "print" we
mean that both a plain text file and a PDF version of that file will be created on
computer B.

PSU is installed and started at deadstart in the turnkey NOS 2.8.7 system available for
Kevin Jordan's version of DtCyber, which can be found [here](https://github.com/kej715/DtCyber).

## Installation
Linux or macOS can be used. Windows is not supported, but it might work, as psuprinter is "pure Python".

You need a Python 3 interpreter to install and run psuprinter. Use of a virtual environment
is recommended. To create a new, empty, virtual environment and activate it, use something like:

    $ cd ~
    $ python3 -m venv tenv
    $ source tenv/bin/activate

Then clone the psuprinter repository to some convenient place, followed by:

    (tenv) $ cd psuprinter
    (tenv) $ pip install .

## Usage
The psuprinter program is not a daemon or anything similar, but an ordinary program that can be
run from the command line. Opening a terminal window specifically for this purpose is recommended.
Whenever the Python virtual environment used for installation is active, it can be run as follows:

    (tenv) $ psuprinter 192.168.1.151 spool

The first argument is the IP address or host name of the computer running DtCyber (running NOS 2.8.7).

The second argument is the name of a directory to which print output files will be written. If this
does not exist, it will be created. This directory will contain plain text versions of the output.
A further subdirectory called PDF will contain the PDF versions.

Both of these arguments are mandatory.

Other optional arguments are:

* -h : Show help information and exit.
* --debug : Output debug information. Hopefully not needed!
* --port : TCP port for PSU on the host to connect to. Default is 2552.
* --portrait : PDF output is landscape by default. Switch to portrait instead.
* -- greenbar : Use a greenbar paper background instead of plain white in the PDF output.
* -- economy : Squeeze more lines on a PDF page, with 6 units between lines instead of 8.

In addition to saving "paper", economy mode is useful for making circles more circular in
ASCII art output and gives better results when printing QR code patterns.

The parameters of a PDF page depend on the options used as follows:

| Options            | Chars per line | Lines per page |
|--------------------|----------------|----------------|
| landscape, normal  | 137            | 67             |
| landscape, economy | 137            | 89             |
| portrait, normal   | 102            | 88             |
| portrait, economy  | 102            | 117            |

Form feed characters are always honoured.
The PDF font used is Courier-Bold.

It is essential that the printer output contains at least one banner page. This is used to
obtain information used to construct the output file names. The file names are of the form:

    NICK.AAJA.AAGC.24_10_06.14_11_18.txt / .pdf

formed from the user name, user hash, job sequence number, date and time separated by periods.

If psuprinter is interrupted with ctrl-C, it will exit cleanly.

## NOS considerations

PSU printer output is often useful for printing documents with lower case characters,
which the default line printer setup will not handle correctly. It is possible to turn
off the line printer(s) and send all printed output to PSU. On the other hand, PSU output
is slower than "normal" line printer output.

Also, correctly handling documents with lower case characters has some complications.

Perhaps the best approach is to write a CCL procedure which deals with these complications
behind the scenes, and assigns a forms code (say, PS) to output that is to go through PSU.
If this forms code is assigned to the PSU printer, lower case documents can go out via PSU
with other output going to the normal line printer.

This is an example of a suitable CCL procedure:

```
.PROC,PSPRINT*I,FN=(*F),TYPE=(*N=PLAIN,*A).
.HELP.
PRINT A 6/12 TEXT FILE TO A PSU PRINTER WITH FORM CODE PS.
.HELP,FN.
ENTER NAME OF FILE TO PRINT.
.HELP,TYPE.
IF LIST TREAT AS LISTING WITH FORMAT EFFECTORS.
.ENDHELP.
.IF,.NOT.FILE(FN,LO),NOFN.
REVERT,ABORT.FILE FN IS NOT LOCAL.
.ENDIF,NOFN.
REWIND,FN.
.IF,STR($TYPE$).EQ.STR($LIST$),DOLIST.
COPYBF,FN,TEMPYY1.
.ELSE,DOLIST.
COPYSBF,FN,TEMPYY1.
.ENDIF,DOLIST.
FCOPY,P=TEMPYY1,N=TEMPYY2,PC=ASCII64,NC=ASCII8,R.
RETURN,TEMPYY1.
ROUTE,TEMPYY2,DC=PR,EC=A9,FC=PS.
REVERT,NOLIST.
EXIT.
REVERT,ABORT.PSPRINT
```

Such a procedure can then be used as follows:

    /PSPRINT,AFILE.

would send AFILE for printing via PSU. AFILE would be assumed to not
have "format effector" characters in column 1, which would be the case
for some document created using FSE, for example. The command:

    /PSPRINT,AFILE,PLAIN.

could also be used for this case.

If a compiler listing or other document with format effectors is to be
printed then:

   /PSPRINT,BFILE,LIST.

should be used.

Assigning a forms code to a PSU printer needs to be done via the NOS console.
The following commands could be used (please refer to CDC manuals for more details):

```
K,NAM.   (start talking to NAM - Network Access Methods)
K.ST.    (get status of NAM components, one of which is PSU)
(Note the JSN for PSU - jsn in what follows)
[  (clear line)
K,jsn.   (talk to PSU control application)
K.FORM,PRINT05,PS  (assign form code PS to the PSU printer set up on the turnkey system)
```

## Example

```
nick@nuc1:~ source ~/tenv/bin/activate
(tenv) nick@nuc1:~ cd temp
(tenv) nick@nuc1:~/temp$ psuprinter

PSUprinter: CDC PSU client
==========================
usage: psuprinter [-h] [--debug] [--port PORT] [--portrait] [--greenbar] [--economy] host outdir
psuprinter: error: the following arguments are required: host, outdir

(tenv) nick@nuc1:~/temp$ psuprinter 192.168.1.151 spool

PSUprinter: CDC PSU client
==========================
Connecting to host - please wait ...
Connected
WELCOME TO THE NOS SOFTWARE SYSTEM.
COPYRIGHT CONTROL DATA SYSTEMS INC. 1994.
24/10/06. 14.04.42. PR02P03
MAINFRAME T1.                           NOS 2.8.7 871/871.
PRINTER SUPPORT UTILITY.      COPYRIGHT CONTROL DATA CORP. 1984.

INFO: created output file: spool/NICK.AAJA.AAGC.24_10_06.14_11_18.txt
INFO: created PDF output file: spool/PDF/NICK.AAJA.AAGC.24_10_06.14_11_18.pdf

INFO: output completed.
```

## Acknowledgement

The plain text to PDF conversion is done by a highly modified version of Anand B. Pillai's
pyText2Pdf Python 2 script. The original (?) version of this can be found 
[here](https://gist.github.com/anonymous/4410965).

## Alternatives

The PDF output is not very flexible. It also doesn't understand the "extended" format effectors
(column 1 characters) CDC uses to do various tricks with listings (especially in banner pages).
It only understands page eject and overprint.

There are now two alternative plain text to PDF converters which are more flexible and/or
understand extended format effectors:

- [virtual1403](https://github.com/racingmars/virtual1403) by Matthew R. Wilson. This is very
  widely used in the retrocomputing world, especially by IBM mainframe aficionados. It is a mature
  and polished program written in Go. The CDC extended format effectors have been added to it
  by William Schaub. 
- [lp2pdf](https://github.com/AndrewHastings/lp2pdf/blob/master/lp2pdf) by Andrew Hastings. This
  is a Perl program that understands the CDC extended format effectors and can also simulate
  DECWriter III and Teletype 33 devices.
  
Both of these can use various fonts that are more appropriate than Courier-Bold to the task of
mimicking a line printer.

It is likely that either could replace the supplied text to PDF program quite easily, as the
current program is simply run "as a command" using Python's subprocess module. The lp2pdf
program could certainly be used in this way.


