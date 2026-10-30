"""Small bounded caches shared by image decoding and reusable puppet meshes."""
from collections import OrderedDict

class LRU(OrderedDict):
    def __init__(self,limit,byte_limit=None,weight=None):
        super().__init__();self.limit=limit;self.byte_limit=byte_limit;self.weight=weight or (lambda value:0);self.bytes=0

    def __getitem__(self,key):
        value=super().__getitem__(key);self.move_to_end(key);return value

    def __setitem__(self,key,value):
        if key in self:del self[key]
        if self.byte_limit is not None and self.weight(value)>self.byte_limit:return
        super().__setitem__(key,value);self.move_to_end(key);self.bytes+=self.weight(value)
        while len(self)>self.limit or (self.byte_limit is not None and self.bytes>self.byte_limit):
            self.popitem(last=False)

    def __delitem__(self,key):
        self.bytes-=self.weight(super().__getitem__(key));super().__delitem__(key)

    def popitem(self,last=True):
        key,value=super().popitem(last=last);self.bytes-=self.weight(value);return key,value

    def clear(self):
        super().clear();self.bytes=0

def image_bytes(image):return image.width*image.height*len(image.getbands())
