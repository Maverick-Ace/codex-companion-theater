"""Independent, seeded walking plans over the usable stage, without home slots."""
def spread(rng,count,left=.09,right=.91):
    places=[left+(right-left)*(i+rng.uniform(.15,.85))/max(1,count) for i in range(count)]
    rng.shuffle(places)
    return places

class Roaming:
    def __init__(self):
        self.plans={}

    def retain(self,world):
        self.plans={a.id:self.plans.get(a.id,{'next':world.t+world.rng.uniform(.8,2.8),'recent':[]}) for a in world.actors}

    def scatter(self,world,actors,left=.09,right=.91):
        for actor,x in zip(actors,spread(world.rng,len(actors),left,right)):
            actor.target=x;actor.depth_target=world.rng.uniform(0,.9)

    def step(self,world):
        if world.t<world.next_roam:return
        for actor in world.actors:
            plan=self.plans[actor.id]
            if world.t<plan['next']:continue
            if actor.interaction or actor.reaction or actor.attention or actor.play:
                plan['next']=world.t+world.rng.uniform(.5,1.2);continue
            if abs(actor.target-actor.x)>.06 and abs(actor.v)>.015:
                plan['next']=world.t+.6;continue
            # Prefer an unvisited part of the stage, with a soft crowd preference.
            # This is not collision avoidance: friends can still cross each other.
            candidates=[world.rng.uniform(.07,.93) for _ in range(10)]
            def score(x):
                recent=min((abs(x-p) for p in plan['recent']),default=.4)
                crowd=min((abs(x-a.target) for a in world.actors if a is not actor),default=.3)
                return min(abs(x-actor.x),.55)+recent*.35+min(crowd,.2)*.25
            candidates=[x for x in candidates if abs(x-actor.x)>.12] or candidates
            actor.target=world.rng.choices(candidates,weights=[1+score(x)*5 for x in candidates],k=1)[0]
            actor.depth_target=world.rng.uniform(0,1)
            plan['recent']=(plan['recent']+[actor.target])[-3:]
            duration=abs(actor.target-actor.x)/max(.07,.13*actor.tempo)
            plan['next']=world.t+max(1.4,duration+world.rng.uniform(.6,2.2))
        world.next_roam=min((p['next'] for p in self.plans.values()),default=world.t+1)
