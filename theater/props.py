"""Shared stage coordinates for artwork and actor contact choreography.

All x values use the same usable-width normalization as character placement.
"""
POSITIONS = {
    'home': {'sofa':.20,'lamp':.08,'teacup':.66,'book':.34,'side_table':.66},
    'office': {'laptop':.52,'desk':.53,'plant':.84,'notebook':.64},
    'dinner': {'hotpot':.50,'dish':.65,'teacup':.30,'table':.50},
    'outing': {'basket':.66,'tent':.18,'picnic':.68,'tree':.89,'teacup':.53},
}
INTERACTIONS = {
    'home': [{'prop':'sofa','action':'sit','x':.20},
             {'prop':'book','action':'read','x':.34},
             {'prop':'teacup','action':'sip','x':.66}],
    'office': [{'prop':'laptop','action':'type','x':.48},
               {'prop':'plant','action':'water','x':.80},
               {'prop':'notebook','action':'write','x':.64}],
    'dinner': [{'prop':'hotpot','action':'stir','x':.43},
               {'prop':'dish','action':'serve','x':.65},
               {'prop':'teacup','action':'sip','x':.30}],
    'outing': [{'prop':'basket','action':'unpack','x':.66},
               {'prop':'tent','action':'inspect','x':.25},
               {'prop':'teacup','action':'sip','x':.53}],
}
HEIGHTS = {'sofa':20,'lamp':64,'teacup':39,'book':44,'laptop':45,
           'desk':43,'plant':40,'notebook':45,'hotpot':33,'dish':24,
           'table':17,'basket':20,'tent':42,'picnic':5,'tree':51,'side_table':29}


def position(x, width, size):
    return int(x*(width-size)+size/2)


def prop_layout(name, width, floor, size):
    unit=max(.65,min(1.8,size/110))
    return {key:{'x':position(x,width,size),'y':floor-HEIGHTS[key]*unit}
            for key,x in POSITIONS.get(name,{}).items()}


def interaction_slots(environment, count):
    """Reserve each object for at most one actor; extra cast members keep company."""
    return [dict(slot) for slot in INTERACTIONS.get(environment,[])[:count]]
