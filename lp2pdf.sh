#!/bin/sh
#echo "HERE."
#./text2pdf.py ${1} -L -c 137 -l 67 -F -G -s 8 -v 8 -q -f Courier-Bold -o ${2}
#./text2pdf.py ${1} -L -c 137 -l 67 -F -s 8 -v 8 -q -f Courier-Bold -o ${2}
#./text2pdf.py ${1} -c 81 -l 66 -F -s 10 -v 10 -q -f Courier -o ${2}
# BEST PORTRAIT ./text2pdf.py ${1} -c 137 -l 67 -F -s 10 -v 10 -q -f Courier -o ${2}
./text2pdf.py ${1} -L -c 137 -l 67 -F -s 8 -v 8 -q -f Courier -o ${2}
