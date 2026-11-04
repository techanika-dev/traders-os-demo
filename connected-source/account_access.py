"""Account sessions and ownership checks for the local learning prototype."""
import copy, hashlib, hmac, secrets, time, re
ORG='Atlas Trading Academy'
DEMOS={'student@demo.vertex':('Student','S1001','Alex Morgan'),'tutor@demo.vertex':('Instructor',None,'Maya Patel'),'admin@demo.vertex':('Organization Admin',None,'Academy admin'),'superadmin@demo.vertex':('Super Admin',None,'Enterprise admin')}

def setup(con):
    con.execute('CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, student TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, identity TEXT NOT NULL, expires REAL NOT NULL)')

def digest(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

def session(con, identity):
    import json
    token=secrets.token_urlsafe(32)
    con.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),json.dumps(identity),time.time()+86400))
    return {'token':token,'user':identity}

def identify(con,token):
    import json
    if not token:return None
    row=con.execute('SELECT identity FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    return json.loads(row[0]) if row else None

def register(con,state,v):
    email=str(v.get('email','')).strip().lower();name=str(v.get('name','')).strip();password=str(v.get('password',''))
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254:raise ValueError('Enter a valid email address.')
    if not name or len(name)>100:raise ValueError('Enter your name (up to 100 characters).')
    if not 10<=len(password)<=128:raise ValueError('Use a password between 10 and 128 characters.')
    if email in DEMOS or con.execute('SELECT 1 FROM accounts WHERE email=?',(email,)).fetchone():raise ValueError('An account already uses this email. Sign in instead.')
    sid='S-'+secrets.token_hex(8);salt=secrets.token_hex(16)
    con.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?)',(sid,email,name,salt,digest(password,salt),sid))
    state[ORG]['students'].append({'id':sid,'name':name,'email':email,'course':'','mentor':'','progress':0,'completed':[],'status':'Active','plan':'Free','joined':time.strftime('%Y-%m-%d'),'notes':'','sharing':False})
    return session(con,{'id':sid,'student':sid,'name':name,'email':email,'role':'Student','org':ORG})

def login(con,v):
    email=str(v.get('email','')).strip().lower();password=str(v.get('password',''))
    if email in DEMOS and hmac.compare_digest(password,'VertexDemo'):
        role,sid,name=DEMOS[email];return session(con,{'id':email,'student':sid,'name':name,'email':email,'role':role,'org':ORG,'demo':True})
    row=con.execute('SELECT id,name,salt,password_hash,student FROM accounts WHERE email=?',(email,)).fetchone()
    if not row or len(password)>128 or not hmac.compare_digest(digest(password,row[2]),row[3]):raise ValueError('Email or password is incorrect.')
    return session(con,{'id':row[0],'student':row[4],'name':row[1],'email':email,'role':'Student','org':ORG})

OWNED=['grants','invoices','subscriptions','submissions','certificates','assessments','studyPlans','learningGoals','skillEvidence','bookings','tickets']
PRIVATE=['leads','users','tasks','workflows','jobs','audit','media','privacyRequests','learningCohorts']
PERSONAL=['notes','bookmarks','trades','positions','watchlist','chat','aiDrafts','groups','chart','settings','following','currentClass']

def project(state,user):
    if user and user['role']!='Student':
        return copy.deepcopy(state if user['role']=='Super Admin' else {user['org']:state[user['org']]})
    d=copy.deepcopy(state[ORG]);sid=user['student'] if user else None
    active={g['course'] for g in d.get('grants',[]) if g.get('student')==sid and g.get('active')}
    # Active all-course membership also covers courses published after checkout.
    if sid and any(s.get('student')==sid and s.get('status')=='Active' and s.get('scope')=='catalogue' for s in d.get('subscriptions',[])):
        active|={c['id'] for c in d['courses'] if c.get('status')=='Published'}
        existing={g['course'] for g in d['grants'] if g.get('student')==sid and g.get('active')}
        d['grants'] += [{'id':'plan-access-'+sid+'-'+cid,'student':sid,'course':cid,'origin':'Active membership','active':True} for cid in active-existing]
    d['courses']=[c for c in d['courses'] if c.get('status')=='Published']
    for c in d['courses']:
        if c['id'] not in active:
            c['lessons']=[{k:v for k,v in l.items() if k in ('id','title','minutes','type')} for l in c.get('lessons',[])]
    d['students']=[s for s in d['students'] if s['id']==sid]
    for k in OWNED:d[k]=[x for x in d.get(k,[]) if x.get('student')==sid] if sid else []
    d['assignments']=[a for a in d.get('assignments',[]) if a.get('course') in active and a.get('published')]
    d['resources']=[a for a in d.get('resources',[]) if a.get('course') in active]
    d['classes']=[c for c in d.get('classes',[]) if c.get('course') in active]
    d['lessonProgress']={k:v for k,v in d.get('lessonProgress',{}).items() if sid and k.startswith(sid+':')}
    d['personalProfiles']={sid:d.get('personalProfiles',{}).get(sid,{})} if sid else {}
    d['savedCourses']={sid:d.get('savedCourses',{}).get(sid,[])} if sid else {}
    d['messages']=[m for m in d.get('messages',[]) if sid and m.get('student')==sid]
    d['notifications']=[n for n in d.get('notifications',[]) if sid and n.get('student')==sid]
    cohorts={c['id'] for c in d.get('learningCohorts',[]) if sid in c.get('members',[])}
    d['announcements']=[a for a in d.get('announcements',[]) if sid and (a.get('target') in ('Everyone','Student') or a.get('target') in {'cohort:'+c for c in cohorts})]
    for a in d['announcements']:a['acknowledged']=[sid] if sid in a.get('acknowledged',[]) else []
    d['officeSlots']=[s for s in d.get('officeSlots',[]) if not s.get('booking') or s['booking'].get('student')==sid] if sid else []
    owncohorts=[{**c,'members':[sid]} for c in d.get('learningCohorts',[]) if c['id'] in cohorts]
    for k in PRIVATE:d[k]=[]
    d['learningCohorts']=owncohorts
    # No admin configuration, notes, journal, AI history, or discussions leak into a new account.
    for k in ['featureSettings','featureRuns','integrations','productBacklog','releaseStatus','decisionNotes','acceptanceNotes','readinessEvidence','personalData']:
        d[k]=[] if isinstance(d.get(k),list) else {}
    personal=state[ORG].get('personalData',{}).get(sid,{}) if sid else {}
    for k in PERSONAL:
        default={'settings':{'brand':'TRADERS OS','notifications':True,'theme':'Light'},'chart':{'symbol':'EURUSD','timeframe':'1H','type':'Candles','indicators':[],'drawings':[],'layout':'Single'}}.get(k,{} if k=='notes' else [])
        d[k]=copy.deepcopy(personal.get(k,default))
    d['posts']=[]
    return {ORG:d}

def checkout(state,user,v):
    if not user or user['role']!='Student':raise PermissionError('Sign in as a student.')
    d=state[ORG];sid=user['student'];kind=v.get('kind');target=v.get('id');today=time.strftime('%Y-%m-%d')
    if kind=='cancel':
        sub=next((s for s in d['subscriptions'] if s['id']==target and s['student']==sid),None)
        if not sub:raise ValueError('Subscription not found.')
        sub['status']='Cancelled'
        next(s for s in d['students'] if s['id']==sid)['plan']='Free'
        for g in d['grants']:
            if g.get('student')==sid and g.get('subscription')==target:g['active']=False
        return
    if kind=='course':
        c=next((c for c in d['courses'] if c['id']==target and c['status']=='Published'),None)
        if not c:raise ValueError('Course is unavailable.')
        if any(g.get('student')==sid and g.get('course')==target and g.get('active') and not g.get('subscription') for g in d['grants']):return
        ids=[target];amount=c['price'];label=c['title'];subid=None
    elif kind=='plan':
        plan=next((p for p in d['plans'] if p['id']==target and p['name']=='Professional'),None)
        if not plan:raise ValueError('Plan is unavailable.')
        if any(s.get('student')==sid and s.get('scope')=='catalogue' and s.get('status')=='Active' for s in d['subscriptions']):return
        ids=[c['id'] for c in d['courses'] if c['status']=='Published'];amount=plan['price'];label=plan['name'];subid='SUB-'+secrets.token_hex(8)
        d['subscriptions'].append({'id':subid,'student':sid,'plan':label,'status':'Active','scope':'catalogue','renewal':'Manual demo renewal','amount':amount,'demo':True})
    else:raise ValueError('Choose a course or membership.')
    for cid in ids:d['grants'].append({'id':'G-'+secrets.token_hex(8),'student':sid,'course':cid,'origin':'Demo membership' if subid else 'Demo course purchase','subscription':subid,'active':True})
    d['invoices'].append({'id':'INV-'+secrets.token_hex(8),'student':sid,'course':target if kind=='course' else '', 'amount':amount,'status':'Demo paid','date':today,'due':today,'refunded':0,'description':label,'demo':True})
    learner=next(s for s in d['students'] if s['id']==sid)
    if not learner.get('course') and ids:learner['course']=ids[0]
    if subid:learner['plan']=label

def student_update(state,user,base,next_state,merge):
    sid=user['student'];org=user['org'];current=state[org];b=base.get(org,{});n=next_state.get(org,{})
    if set(base)!= {org} or set(next_state)!={org}:raise PermissionError('Account scope mismatch.')
    projection=project(state,user)[org]
    # Validate changes only; unchanged stale snapshots are allowed for three-way merge.
    allowed=set(PERSONAL+['students','submissions','assessments','certificates','learningGoals','skillEvidence','bookings','tickets','lessonProgress','savedCourses','personalProfiles','audit','notifications','officeSlots','announcements','messages'])
    changed={k for k in b.keys()|n.keys() if b.get(k)!=n.get(k)}
    if changed-allowed:raise PermissionError('This operation requires academy access or checkout.')
    active={g['course'] for g in projection['grants'] if g.get('active')}
    for key in changed:
        if key=='audit':continue
        if key in PERSONAL:
            personal=current.setdefault('personalData',{}).setdefault(sid,{})
            personal[key]=merge(b.get(key),n.get(key),projection.get(key));continue
        if key=='students':
            if len(n[key])!=1 or n[key][0].get('id')!=sid:raise PermissionError('Student ownership mismatch.')
            old=b[key][0];new=n[key][0]
            if any(old.get(k)!=new.get(k) for k in old.keys()|new.keys() if k not in ('progress','completed','sharing')):raise PermissionError('Protected student field.')
            actual=next(s for s in current['students'] if s['id']==sid)
            for k in ('progress','completed','sharing'):
                if old.get(k)!=new.get(k):actual[k]=merge(old.get(k),new.get(k),actual.get(k))
            continue
        if key in ('lessonProgress','savedCourses','personalProfiles'):
            for k,v in n.get(key,{}).items():
                if not (k==sid if key in ('savedCourses','personalProfiles') else k.startswith(sid+':') and k[len(sid)+1:] in active):raise PermissionError('Course access is required.')
                if key=='lessonProgress':
                    course=next(c for c in current['courses'] if c['id']==k[len(sid)+1:])
                    if not isinstance(v,list) or any(type(i)!=int or i<0 or i>=len(course['lessons']) for i in v):raise ValueError('Invalid lesson progress.')
            merged=merge(b.get(key,{}),n.get(key,{}),projection.get(key,{}));current.setdefault(key,{}).update(merged);continue
        if key=='officeSlots':
            oldmap={x['id']:x for x in b[key]};newmap={x['id']:x for x in n[key]}
            if set(oldmap)!=set(newmap):raise PermissionError('Only tutors publish slots.')
            for id,x in newmap.items():
                old=oldmap[id]
                if x==old:continue
                if any(old.get(k)!=x.get(k) for k in old.keys()|x.keys() if k not in ('booking','status')):raise PermissionError('Slot fields are protected.')
                if x.get('booking') and (x['booking'].get('student')!=sid or set(x['booking'])-{'student','agenda'}):raise PermissionError('Booking ownership mismatch.')
                if x.get('status')!=('Booked' if x.get('booking') else 'Available'):raise PermissionError('Invalid booking status.')
                actual=next(s for s in current[key] if s['id']==id)
                if actual.get('status')=='Completed':raise PermissionError('Completed appointment is locked.')
                replacement=merge(old,x,actual);actual.clear();actual.update(replacement)
            continue
        if key=='announcements':
            for x in n[key]:
                old=next((a for a in b[key] if a['id']==x['id']),None)
                if not old or any(old.get(k)!=x.get(k) for k in old if k!='acknowledged') or x.get('acknowledged') not in ([],[sid]):raise PermissionError('Only acknowledgement is allowed.')
                if old!=x:
                    actual=next(a for a in current[key] if a['id']==x['id']);actual['acknowledged']=list(set(actual.get('acknowledged',[])+[sid]))
            continue
        if key in ('submissions','skillEvidence'):
            supplied={x['id'] for x in n.get(key,[])}
            if any(x['id'] not in supplied and x.get('status') in ('Graded','Demonstrated','Developing','Needs revision') for x in projection.get(key,[])):raise PermissionError('Reviewed work cannot be deleted by the learner.')
        oldmap={x['id']:x for x in b.get(key,[])}
        for x in n.get(key,[]):
            existing=next((z for z in current.get(key,[]) if z.get('id')==x.get('id')),None)
            if existing and existing.get('student')!=sid:raise PermissionError('Record belongs to another account.')
            if key=='notifications' and x['id'] not in oldmap:x['student']=sid
            if key=='messages' and x!=oldmap.get(x['id']):
                if x.get('from')!='Student' or x.get('to') not in ('Instructor','Organization Admin'):raise PermissionError('Invalid message sender or recipient.')

        for x in n.get(key,[]):
            old=oldmap.get(x['id'])
            if old==x:continue
            if x.get('student')!=sid:raise PermissionError('Record ownership mismatch.')
            if key=='submissions':
                a=next((a for a in current.get('assignments',[]) if a['id']==x.get('assignment')),None)
                if not a or a.get('course') not in active or not a.get('published'):raise PermissionError('Assignment access required.')
                if x.get('status')!='Submitted' or x.get('score') not in (None,'') or x.get('feedback') not in (None,''):raise PermissionError('Only tutors can grade work.')
                if old and old.get('status')=='Graded':raise PermissionError('Graded submission is locked.')
            if key=='skillEvidence' and (x.get('status')!='Submitted' or x.get('feedback')):raise PermissionError('Only tutors assess evidence.')
        merged=merge(b.get(key,[]),n.get(key,[]),projection.get(key,[]))
        foreign=[x for x in current.get(key,[]) if x.get('student')!=sid]
        current[key]=foreign+merged
    current.setdefault('audit',[]).insert(0,{'id':'AUD-'+secrets.token_hex(8),'actor':user['email'],'action':'Student records updated','date':time.strftime('%H:%M:%S'),'scope':org})
