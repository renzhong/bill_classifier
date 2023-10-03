#!/bin/bash
iconv --list | sed 's/\/\/$//' | sort > encodings.list
for a in `cat encodings.list`; do
printf "$a "
iconv -f $a -t UTF-8 /Users/devin.zhang/Downloads/账单/八月/zrz_alipay.csv > /dev/null 2>&1 \
&& echo "ok: $a" || echo "fail: $a"
done | tee result.txt

# iconv -f GB18030 -t UTF-8 systeminfo.txt > 2222.txt
