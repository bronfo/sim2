#coding:utf-8

import logging
import asyncio
import websockets

from itertools import cycle
import base64

logging.basicConfig(format='%(asctime)s %(filename)s %(lineno)s: %(message)s')

BUFSIZE = 8196

class MsgType:
    Connect = 1
    Connect_OK = 2
    Connect_Failure = 3
    Data = 4
    Disconnect = 5
    CloseTunnel = 6
    
    FlagToClose = 911
    KEY = b'xky0810'
    
    def pack(type, stream_id, data):
        d = bytes([type]) + stream_id + data
        return MsgType.crypt(d, MsgType.KEY, True)
    
    def unpack(data):
        data = MsgType.crypt(data, MsgType.KEY, False)
        return data[0], data[1:5], data[5:]
    
    def setaddr(host, port):
        return ('%s:%d' % (host, port)).encode()
    
    def getaddr(data):
        try:
            host, port = data.split(b':')
            return host, int(port)
        except Exception:
            return None, None
    
    # bytes data
    def crypt(data, key, encode=True):
        # python2 has izip, python3 has zip
        izip = zip
        # to bytes
        #data = data.encode()
        if not encode:
            data = base64.b64decode(data)
        #xored = ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(data, cycle(key)))
        xored = b''.join(bytes([x ^ y]) for (x,y) in izip(data, cycle(key)))
        return base64.b64encode(xored) if encode else xored


class Stream:
    def __init__(self, server, stream_id, data):
        self.server = server
        self.stream_id = stream_id
        self.data = data
        self.write_queue = asyncio.Queue()
    
    async def run(self):
        try:
            self.host, self.port = MsgType.getaddr(self.data)
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port)
        except Exception:
            logging.error('connect websocket with error ==>', exc_info=True)
            msg = MsgType.pack(MsgType.Connect_Failure,
                self.stream_id, b'')
            await self.server.send_queue.put(msg)
            del self.server.stream_map[self.stream_id]
            return
        
        logging.error('connect %s:%d OK' % (self.host, self.port))
        
        msg = MsgType.pack(MsgType.Connect_OK, self.stream_id, b'')
        await self.server.send_queue.put(msg)
        
        await asyncio.wait([self.read_from_remote(), self.write_to_remote()])
    
    async def read_from_remote(self):
        while True:
            try:
                data = await self.reader.read(BUFSIZE)
            except Exception:
                logging.error('read from remote with ex ==>', exc_info=True)
                data = b''
            
            logging.error('read [%s] from remote' % data[:16])
            
            if data:
                msg = MsgType.pack(MsgType.Data, self.stream_id, data)
                await self.server.send_queue.put(msg)
            else:
                msg = MsgType.pack(MsgType.Disconnect, self.stream_id, b'')
                await self.server.send_queue.put(msg)
                return
    
    
    async def write_to_remote(self):
        while True:
            msg = await self.write_queue.get()
            logging.error('writing [%s] to remote' %
                (msg[:16] if type(msg)==bytes else msg))
            if msg == MsgType.FlagToClose:
                self.do_close()
                return
            
            try:
                self.writer.write(msg)
                await self.writer.drain()
            except Exception:
                self.do_close()
                return
    
    def do_close(self):
        if not self.writer.transport.is_closing():
            self.writer.write_eof()
        if self.stream_id in self.server.stream_map:
            del self.server.stream_map[self.stream_id]

class Server:
    def __init__(self, ws):
        self.ws = ws
        self.stream_map = {}
        self.send_queue = asyncio.Queue()
    
    async def run(self):
        logging.error('new websocket connection, one Server, startup send_to_peer, reading...')
        send_task = asyncio.ensure_future(self.send_to_peer())
        await self.read_from_peer()
        logging.error('websocket read end')
        send_task.cancel()
    
    async def send_to_peer(self):
        while True:
            data = await self.send_queue.get()
            logging.error('queue [%s], sending to websocket' % data[:16])
            try:
                await self.ws.send(data)
            except Exception:
                logging.error('sending to websocket with error ==>', exc_info=True)
                return

    async def read_from_peer(self):
        while True:
            try:
                data = await self.ws.recv()
                logging.error('read from websocket: %s' % data[:16])
            except Exception:
                logging.error('read from websocket with error ==>', exc_info=True)
                return
            
            type, stream_id, data = MsgType.unpack(data)
            stm = 'found stream' if stream_id in self.stream_map else 'nofound stream'
            logging.error('stream=%s' % stm)
            
            if type == MsgType.Connect:
                logging.error('read Connect request')
                stream = Stream(self, stream_id, data)
                self.stream_map[stream_id] = stream
                asyncio.ensure_future(stream.run())
            
            elif type == MsgType.Disconnect:
                if stream_id in self.stream_map:
                    await self.stream_map[stream_id
                        ].write_queue.put(MsgType.FlagToClose)
            elif type == MsgType.Data:
                if stream_id in self.stream_map:
                    await self.stream_map[stream_id
                        ].write_queue.put(data)
            else:
                logging.error('websocket get unexpected msg')


async def websocket_handle(ws, path):
    server = Server(ws)
    try:
        await server.run()
        logging.error('tunnel closed')
    except Exception:
        logging.error('server.run exception')

async def main():
    server = await websockets.serve(websocket_handle, '', 8080)
    await server.wait_closed()


if __name__ == '__main__':
    logging.disable(logging.WARNING)
    asyncio.get_event_loop().run_until_complete(main())
