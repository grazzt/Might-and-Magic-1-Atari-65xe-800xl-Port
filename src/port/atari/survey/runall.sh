#!/bin/sh
cd ~/coding/mightandmagic
for r in bitmap_lo matrix_lo bitmap_hi; do
  for t in $(ls tools/traces/*.txt | xargs -n1 basename | sed 's/\.txt$//' | grep -v -E "capture-entry|snapshot|title-scenes"); do
    echo "$t $r"
  done
done | xargs -P 8 -L1 sh -c 'python3 /tmp/opencode/survey/clobber.py $0 $1 > /tmp/opencode/survey/cl/$0.$1.txt 2>&1'
echo done > /tmp/opencode/survey/cl/ALLDONE
