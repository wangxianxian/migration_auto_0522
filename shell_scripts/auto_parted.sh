#!/usr/bin/env bash
parted $1 << EOF
mklabel gpt
mkpart 0 1m 2g
mkpart 1 2g 4g
mkpart 2 4g 6g
mkpart 3 6g 8g
mkpart 4 8g 10g
mkpart 5 10g 12g
mkpart 6 12g 14g
mkpart 7 14g 16g
p
q
<< EOF