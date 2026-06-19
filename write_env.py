#!/usr/bin/env python3
import pathlib
content = '# Set your IQ Option credentials here. Do not commit this file to version control.\nIQ_OPTION_EMAIL=agolfhitler3000@gmail.com\nIQ_OPTION_PASSWORD=MynameisPeter1!\n'
pathlib.Path('/root/iqoption-bot/.env').write_text(content)
print("Written OK")
