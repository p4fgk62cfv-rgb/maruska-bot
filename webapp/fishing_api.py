"""Fishing Mini App API, served by Maruska's existing aiohttp server."""
import json, secrets
from aiohttp import web
from sqlalchemy import text
from database.database import session_scope
from webapp.telegram_auth import verify_init_data

DEFAULT_STATE = {
    'diamonds': 1250, 'xp': 0, 'level': 1, 'caught': 0, 'best': 0,
    'inventory': {}, 'legendary': 0, 'nightCatches': 0, 'unlockedAchievements': [],
    'baitStock': {'worm':12,'maggots':5,'corn':5,'bread':5,'livebait':3,'fly':3,'wobbler':2,'spinner':2,'softbait':2},
    'boat':'shore', 'ownedBoats':['shore'], 'streak':0, 'lastFishDay':'', 'questsDay':'',
    'quests':[], 'chests':0, 'openedChests':0, 'lifetimeWeight':0,
}
FISH = {
    'pike':(.8,8.8,320),'perch':(.15,2.1,90),'crucian':(.12,1.8,70),'roach':(.08,1.3,55),
    'carp':(1.5,12,620),'tench':(.3,3.4,180),'bream':(.4,4.8,210),'zander':(.7,6.2,390),
    'asp':(.8,5.6,360),'catfish':(3,25,1250),'chub':(.4,3.5,200),'burbo':(.6,5.8,410),
    'trout':(.5,6,700),'taimen':(2,18,1600),'beluga':(8,35,3000),
}

def _auth(request):
    parsed = verify_init_data(request.headers.get('X-Telegram-Init-Data',''), request.app['bot_token'])
    if parsed is None:
        raise web.HTTPUnauthorized(text='bad Telegram initData')
    uid = (parsed.get('user') or {}).get('id')
    if not uid:
        raise web.HTTPUnauthorized(text='no Telegram user')
    return int(uid)

async def profile(request):
    uid=_auth(request)
    async with session_scope() as session:
        row=(await session.execute(text('SELECT state_json FROM fishing_players WHERE user_id=:uid'),{'uid':uid})).first()
        if row is None:
            state=dict(DEFAULT_STATE)
            await session.execute(text("INSERT INTO fishing_players(user_id,state_json) VALUES(:uid,CAST(:state AS jsonb))"),{'uid':uid,'state':json.dumps(state)})
            await session.commit()
        else:
            state=dict(row[0] or {})
    return web.json_response(state)

async def save_profile(request):
    uid=_auth(request)
    try: state=await request.json()
    except Exception: raise web.HTTPBadRequest(text='bad json')
    if not isinstance(state,dict): raise web.HTTPBadRequest(text='state must be object')
    async with session_scope() as session:
        await session.execute(text('''INSERT INTO fishing_players(user_id,state_json) VALUES(:uid,CAST(:state AS jsonb))
            ON CONFLICT(user_id) DO UPDATE SET state_json=EXCLUDED.state_json,updated_at=CURRENT_TIMESTAMP'''),{'uid':uid,'state':json.dumps(state)})
        await session.commit()
    return web.json_response({'ok':True})

async def record_catch(request):
    uid=_auth(request)
    try: data=await request.json()
    except Exception: raise web.HTTPBadRequest(text='bad json')
    key=str(data.get('fish_key',''))
    try: weight=float(data.get('weight'))
    except (TypeError,ValueError): raise web.HTTPBadRequest(text='bad weight')
    if key not in FISH: raise web.HTTPBadRequest(text='unknown fish')
    lo,hi,base=FISH[key]
    if not lo<=weight<=hi: raise web.HTTPBadRequest(text='weight outside fish range')
    rid=str(data.get('request_id') or secrets.token_hex(16))[:128]
    reward=max(1,round(base*(0.65+0.35*(weight-lo)/max(hi-lo,0.001))))
    async with session_scope() as session:
        old=(await session.execute(text('SELECT id,reward FROM fishing_catches WHERE request_id=:rid'),{'rid':rid})).first()
        if old: return web.json_response({'ok':True,'idempotent':True,'reward':int(old[1]),'id':int(old[0])})
        row=(await session.execute(text('''INSERT INTO fishing_catches(user_id,fish_key,weight,reward,request_id)
            VALUES(:uid,:key,:weight,:reward,:rid) RETURNING id'''),{'uid':uid,'key':key,'weight':weight,'reward':reward,'rid':rid})).first()
        await session.commit()
    return web.json_response({'ok':True,'idempotent':False,'reward':reward,'id':int(row[0])})

async def leaderboard(request):
    _auth(request)
    async with session_scope() as session:
        rows=(await session.execute(text('''SELECT user_id,COUNT(*) AS catches,MAX(weight) AS best_weight
            FROM fishing_catches GROUP BY user_id ORDER BY best_weight DESC LIMIT 50'''))).mappings().all()
    return web.json_response([dict(r) for r in rows])

def setup_fishing_routes(app):
    app.router.add_get('/api/fishing/profile', profile)
    app.router.add_put('/api/fishing/profile', save_profile)
    app.router.add_post('/api/fishing/catch', record_catch)
    app.router.add_get('/api/fishing/leaderboard', leaderboard)
