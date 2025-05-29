#

from urllib import request

def add_verilog_file(plat, file_name):
    URL_FMT = "https://raw.githubusercontent.com/ZipCPU/wb2axip/master/rtl/{}"
    if file_name not in plat.extra_files:
        url = URL_FMT.format(file_name)
        content = request.urlopen(url).read()
        plat.add_file(file_name, content)
