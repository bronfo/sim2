#coding:utf-8
#import SimpleHTTPServer
import SocketServer
import BaseHTTPServer
import socket
from urlparse import urlparse
import httplib
import os
import logging

PORT = 8080
RDBUFSZ = 10240

g_id = 0
g_connects = {}

logger = logging.getLogger(os.path.basename(__file__))


def crypt_string(data, encode=True, key='bjisa8g9kx7d8sskdg898d_xvc87d*84@*&x'):
    from itertools import izip, cycle
    import base64
    if not encode:
        data = base64.decodestring(data)
    xored = ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(data, cycle(key)))
    if encode:
        return base64.encodestring(xored).strip()
    return xored

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    #protocol_version = 'HTTP/1.1'
    # todo id -- peer ip:port
    def log_message(self, format, *args):
        return
    
    def set_header(self, status, len):
        self.send_response(status)
        #self.send_header("Connection", "keep-alive")
        #self.send_header("Content-Length", str(len))
        self.end_headers()
    
    def do_GET(self):
        global g_id
        global g_connects
        if self.path.startswith("/connect/"):
            try:
                host, port = crypt_string(self.path[9:], False).split(":")
                conn_to_target = socket.create_connection((host, int(port)))
            except Exception, ex:
                self.send_response(503)
                self.end_headers()
                return
            g_id += 1
            this_id = g_id
            g_connects[str(this_id)] = {'conn': conn_to_target}
            data = 'hello %d' % this_id
            self.set_header(200, len(data))
            self.wfile.write(data)
        elif self.path.startswith("/fetch/"):
            id_str = self.path[7:]
            #logger.info(id_str + " fetching")
            data = ""
            try:
                data = g_connects[id_str]['conn'].recv(RDBUFSZ)
            except Exception, ex1:
                logger.debug("read from target fail")
            try:
                if data:
                    data = crypt_string(data)
                    self.set_header(200, len(data))
                    self.wfile.write(data)
                    logger.debug("%s fetch [%d]" % (id_str, len(data)))
                else:
                    self.set_header(200, 0)
                self.wfile.flush()
            except Exception, ex2:
                self.wfile._wbuf = [] # make finish() happy to flush it
                logger.debug("write to client fail, clean it")
        elif self.path.startswith("/get/"):
            url = crypt_string(self.path[5:], False)
            p = urlparse(url)
            addr = p.netloc.split(":")
            if len(addr) > 1:
                host, port = addr
            else:
                host = addr[0]
                port = 80
            conn = httplib.HTTPConnection(host, int(port))
            conn.request("GET", p.path + "?" + p.query)
            resp = conn.getresponse()
            data = resp.read()
            cnt = str(len(data))
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() == "content-length":
                    if cnt != v:
                        logger.info("len: %s/%s" % (v, cnt))
                    self.send_header(k, v)
                elif k.lower() == "transfer-encoding" and v.lower() == "chunked":
                    self.send_header("Content-Length", cnt)
                else:
                    self.send_header(k, v)
            self.end_headers()
            if data:
                self.wfile.write(data)
        elif self.path == "/":
            data = "test success 12"
            self.set_header(200, len(data))
            self.wfile.write(data)
        else:
            self.send_response(403)

    def do_POST(self):
        if self.path.startswith("/post/"):
            id_str = self.path[6:]
            content_len = int(self.headers.getheader('content-length', 0))
            if content_len > 0:
                content = self.rfile.read(content_len)
                logger.info(id_str + " post [%d/%d]" % (content_len, len(content)))
                g_connects[id_str]['conn'].sendall(crypt_string(content, False))
            else:
                logger.info(id_str + " post [0]?")
            self.set_header(200, 2)
            self.wfile.write('ok')
        else:
            self.set_header(404, 0)

Handler = MyHandler

logging.basicConfig(format='%(asctime)s %(filename)s %(lineno)s: %(message)s')
logger.setLevel(logging.DEBUG)

class MyHTTPServer(SocketServer.ThreadingMixIn,
  BaseHTTPServer.HTTPServer):
    pass

httpd = MyHTTPServer(("", PORT), Handler)

logger.info("serving v3 at port %d" % PORT)
httpd.serve_forever()
