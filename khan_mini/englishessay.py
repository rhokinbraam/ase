import cherrypy
from cherrypy import request
from cherrypy import _cperror
from settings import *
import essaylib.db as db
import hashlib
from essaylib.saplugin import SAEnginePlugin, SATool
from sqlalchemy import and_, or_, asc, desc
import datetime,time
import random, math
import essaylib.scoring as scoring
import numpy
from essaylib.mysqlsession import MySQLSession


MARKINGREPETITIONS = 3
# Jinja templating engine
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))

        
def handle_error():
    cherrypy.response.status = 500
    cherrypy.response.body = [env.get_template('error.html').render({'error':_cperror.format_exc()}) ]


class EnglishEssay(object):   
    _cp_config = {'request.error_response': handle_error}     

    def getState(self):
        conn = request.db
        sql = "select distinct state from assignment"
        state = [s['state'] for s in conn.execute(sql).fetchall()]
        states = [s for s in state if s not in ('READY','COMPLETED')]
        result = None
        if(len(states)>1):
            raise Exception("State error:",states)
        elif len(states)==0:
            result = 'READY'
        else:    
            result = states[0]  
        return result

        
    @cherrypy.expose    
    def index(self, username=None, essayeval_id=None, saved="0"):
        if username == None:
            username = cherrypy.session.get('username', None)
            if username == None:
                raise cherrypy.HTTPRedirect("/login")
        conn = request.db
        state = self.getState()
        if state=='BUSY':
            a = self.activeAssignment(conn, 'BUSY')
            esql = db.essayTable.select(and_(db.essayTable.c.student_name == username, db.essayTable.c.assignment_id == a['id']))
            e = conn.execute(esql).fetchall()
            
            secondsSinceStarted = time.time() - time.mktime(time.strptime(a['startdatetime'],'%Y-%m-%d %H:%M:%S') )  
            duration  = a['duration']
            timeremaining = duration*60 - secondsSinceStarted 
            timeremaining = int(max(timeremaining, 0))
            
            essay_text = e[0]['essay_text'] if len(e)>0 else ''
            return env.get_template('studentbusy.html' ).render({'username':username, 'asm':a,'essay_text':essay_text,'timeremaining': timeremaining, 'saved':saved}) 
        elif state=='MARKING':
            a = self.activeAssignment(conn, 'MARKING')
            done = False
            esql = db.essayEvalTable.select(and_(db.essayEvalTable.c.student_name == username, db.essayEvalTable.c.assignment_id == a['id'])).order_by(db.essayEvalTable.c.id)
            e = conn.execute(esql).fetchall()
            if(len(e)==0):
                return env.get_template('studentmessage.html').render({'username':username,'heading':'No essays to mark','message':'Maybe you logged in with the wrong username?'})    
            ids = [i['id'] for i in e]
            if essayeval_id == None:
                i = 0
            else:
                evalid = int(essayeval_id)
                if evalid in ids:
                    i = ids.index(evalid)
                    if i == len(ids)-1:
                       done = True
                    else:
                       i = i + 1   
                else:
                    i = 0
            essay1_id = e[i]['essay1_id']
            essay2_id = e[i]['essay2_id']                     
            essay1_text = self.getEssayText(conn, e[i]['essay1_id'])
            essay2_text = self.getEssayText(conn, e[i]['essay2_id'])
            score2 = e[i]['score2']
            if score2 == None:
                 score2 = 0.5
            if not done:     
                comment1pos = self.getCommentText(conn, essay1_id, username, 1)     
                comment1neg = self.getCommentText(conn, essay1_id, username, -1)     
                comment2pos = self.getCommentText(conn, essay2_id, username, 1)     
                comment2neg = self.getCommentText(conn, essay2_id, username, -1)                                         
                     
                p = {'username':username, 'essay1_text':essay1_text, 'essay2_text':essay2_text, 'essayeval_id':ids[i],'asm':a,'score':score2,'essay1_id': essay1_id,'essay2_id': essay2_id, 'comment1pos':comment1pos,'comment1neg':comment1neg, 'comment2pos':comment2pos,'comment2neg':comment2neg}  
                return env.get_template('studentmarking.html').render(p) 
            else:
                return env.get_template('studentmessage.html').render({'username':username,'heading':'Done marking','message':'Well done!'})    
        else:
            esql = db.essayTable.select(db.essayTable.c.student_name == username).order_by(desc(db.essayTable.c.submitteddatetime))
            rows = conn.execute(esql).fetchall()
            return env.get_template('studentready.html').render({'username':username,'rows':rows}) 

    def activeAssignment(self,conn, state):
        asql = db.assignmentTable.select(db.assignmentTable.c.state == state)
        a = conn.execute(asql).fetchone()
        return a
     
    def getEssayText(self,conn, essayid):
        esql = db.essayTable.select(db.essayTable.c.id == essayid)
        e = conn.execute(esql).fetchone()
        if(e == None):
            result = ""
        else:
            result = e['essay_text']
        return result

    def getCommentText(self,conn, essayid, username, commenttype):
        esql = "select comment_text from comments where essay_id = %s and student_name='%s' and comment_type=%s " % (essayid, username, commenttype)
        e = conn.execute(esql).fetchone()
        if(e == None):
            result = ""
        else:
            result = e['comment_text']
        return result

    @cherrypy.expose
    def evalEssay(self, scorerange, essayeval_id, pcomment1, pcomment2, ccomment1, ccomment2, bsubmit,pcountdown1, pcountdown2, ccountdown2, ccountdown1, essay1_id, essay2_id ):
        username = cherrypy.session.get('username',None)
        if  username == None:
             raise cherrypy.HTTPRedirect("/login")
        if(self.getState() == 'MARKING'):     
            conn = request.db
            sql = db.essayEvalTable.update().where(db.essayEvalTable.c.id == essayeval_id).values({'score1': 1.0-float(scorerange), 'score2':float(scorerange)})
            conn.execute(sql)
            self.submitComment(essay1_id, pcomment1, 1, username)
            self.submitComment(essay2_id, pcomment2, 1, username)
            self.submitComment(essay1_id, ccomment1, -1, username)
            self.submitComment(essay2_id, ccomment2, -1, username)
        return self.index(essayeval_id = essayeval_id)


    @cherrypy.expose
    def submitAssignment(self, essay_text, assignmentid, bsubmit):
        username = cherrypy.session.get('username',None)
        if  username == None:
             raise cherrypy.HTTPRedirect("/login")
        if(self.getState() == 'BUSY'):     
            conn = request.db

            sql = db.essayTable.delete().where(and_(db.essayTable.c.assignment_id == assignmentid,db.essayTable.c.student_name == username))
            conn.execute(sql)

            submitteddatetime = (datetime.datetime.now().isoformat(' '))[:19]
            sql = db.essayTable.insert().values({'student_name':username,'assignment_id':assignmentid,'essay_text':essay_text,'submitteddatetime':submitteddatetime})
            conn.execute(sql)
        raise cherrypy.HTTPRedirect("index?saved=1")
    
    def submitComment(self, essay_id, pcomment, comment_type,username):
        conn = request.db
        submitteddatetime = (datetime.datetime.now().isoformat(' '))[:19]
        
        sql = "delete from comments where essay_id = %s and student_name='%s' and comment_type=%s" % (int(essay_id), username, int(comment_type))
        conn.execute(sql)
        if(len(pcomment.strip())):
            sql =  db.commentTable.insert().values({'essay_id':essay_id, 'comment_text':pcomment,'comment_type':int(comment_type),'submitteddatetime':submitteddatetime, 'student_name':username})
            conn.execute(sql)
    
    @cherrypy.expose    
    def viewessay(self, essayid):
        username = cherrypy.session.get('username',None)
        if  username == None:
             raise cherrypy.HTTPRedirect("/login")
        conn = request.db
        sql = "select assignment_id from essay where id = %s" % (int(essayid))
        assignmentid = conn.execute(sql).fetchone()[0]
        
        rowsSql = db.essayTable.select(db.essayTable.c.id == essayid)
        row = conn.execute(rowsSql).fetchone()
        
        result_row = {'id':row['id'],'student_name':row['student_name'], 'grade':self.saferound(row['grade'],0), 'essay_text':row['essay_text'],'submitteddatetime':row['submitteddatetime']}

        # figure out the next and previous essay id
        idSql = db.essayTable.select(db.essayTable.c.student_name == username)
        ids = conn.execute(idSql).fetchall()
        ids = [i[0] for i in ids]
        i = ids.index(int(essayid))
        previousid =  ids[len(ids)-1] if i == 0 else ids[i-1]
        nextid =  nextid = ids[0] if i == len(ids)-1 else ids[i+1]

        sql = db.assignmentTable.select(db.assignmentTable.c.id == assignmentid)
        assignmentTitle = conn.execute(sql).fetchone()['title']
        
        sql = "select * from comments where essay_id = %s and comment_type=1" % (int(essayid))
        positive = conn.execute(sql).fetchall()

        sql = "select * from comments where essay_id = %s and comment_type=-1" % (int(essayid))
        negative = conn.execute(sql).fetchall()

          
        result = env.get_template('studentviewessay.html').render({'row':result_row,'assignmentid':assignmentid,'assignmentTitle':assignmentTitle, 'previousid':previousid, 'nextid':nextid,'negative':negative, 'positive':positive})
        return result


    @cherrypy.expose    
    def admin(self, password=None, bsubmit=None):
        result = ''
        conn = request.db
        if (not cherrypy.session.get('admin',False)):
            if (password == None):
                return env.get_template('adminlogin.html').render() 
            elif hashlib.sha224(password).hexdigest() == getPasswordHash(conn):
                cherrypy.session['admin'] = True
            else:     
                return env.get_template('adminlogin.html').render() 
        rowSql = db.assignmentTable.select().order_by(db.assignmentTable.c.id.desc())
        rows = conn.execute(rowSql).fetchall()
        message = cherrypy.session.get('message','')
        cherrypy.session['message'] = ''
        result = env.get_template('adminassignments.html').render({'rows':rows,'message':message})
        return result


    def saferound(self,aFloat, dec):
        if aFloat != None:
             aFloat = round(aFloat, dec)
        return aFloat     

    @cherrypy.expose    
    def adminessayresults(self, assignmentid, complete="0"):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()
        conn = request.db
        rowsSql = db.essayTable.select(db.essayTable.c.assignment_id == assignmentid)
        if complete=="1":
             rowsSql = rowsSql.order_by(desc(db.essayTable.c.score))
        else:     
             rowsSql = rowsSql.order_by(asc(db.essayTable.c.student_name))
        
        rows = conn.execute(rowsSql).fetchall()
        results = []
        
        for row in rows:
            result_row = {'id':row['id'],'student_name':row['student_name'], 'score':self.saferound(row['score'],2), 'essay_text':row['essay_text'],'submitteddatetime':row['submitteddatetime']}
            if row['grade'] == None: 
                result_row['grade'] =None 
            else: 
                result_row['grade'] = round(row['grade'],0)
            essayid =  row['id']
            result_row['comment_count'] = self.getCommentCount(conn, essayid)
            results.append(result_row) 	
            		
        if len(rows)>0:   		
            lowscore = self.saferound(results[len(rows)-1]['score'],2)
            highscore = self.saferound(results[0]['score'],2)
            lowgrade =  results[len(rows)-1]['grade']
            highgrade =  results[0]['grade']
        else:
            lowscore = 0; highscore = 0; lowgrade = None; highgrade = None    
        
        if lowgrade == None:
            lowgrade = 40
        if highgrade == None:
            highgrade = 80                   

        sql = db.assignmentTable.select(db.assignmentTable.c.id == assignmentid)
        assignmentTitle = conn.execute(sql).fetchone()['title']
        result = env.get_template('adminessayresults.html').render({'rows':results, 'assignmentTitle':assignmentTitle,'assignmentid':assignmentid, 'lowscore':lowscore, 'highscore':highscore, 'lowgrade':lowgrade, 'highgrade':highgrade,'complete':complete })
        return result
    
    
    def getCommentCount(self, conn, essayid):
	    sql = db.commentTable.select(db.commentTable.c.essay_id == essayid)
	    rows = conn.execute(sql).fetchall() 
	    return len(rows)
    
    
    @cherrypy.expose
    def adminessayviewmarking(self,assignmentid):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()

        try:
             assignmentid = float(assignmentid)
        except:
             return env.get_template('adminlogin.html').render()
             
        conn = request.db
        esql = """select student_name, sum(case when score1 is not null and score2 is not null then 1 else 0 end) num_submitted, count(1) repetitions
                  from essay_eval where assignment_id = %s  group by student_name""" % (assignmentid) 
        rows = conn.execute(esql).fetchall()
        sql = db.assignmentTable.select(db.assignmentTable.c.id == assignmentid)
        assignmentTitle = conn.execute(sql).fetchone()['title']

        result = env.get_template('adminmarkingresults.html').render({'rows':rows,'assignmentTitle':assignmentTitle,'assignmentid':assignmentid})
        return result        


    @cherrypy.expose    
    def adminviewessay(self, assignmentid, essayid):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()
        conn = request.db
        rowsSql = db.essayTable.select(and_(db.essayTable.c.assignment_id == assignmentid, db.essayTable.c.id == essayid))
        row = conn.execute(rowsSql).fetchone()
        
        result_row = {'id':row['id'],'student_name':row['student_name'], 'grade':self.saferound(row['grade'],0), 'essay_text':row['essay_text'],'submitteddatetime':row['submitteddatetime']}
       
        positivesql = db.commentTable.select(and_(db.commentTable.c.essay_id == essayid, db.commentTable.c.comment_type == 1))
        positive = conn.execute(positivesql).fetchall()
        

        constructivesql = db.commentTable.select(and_(db.commentTable.c.essay_id == essayid, db.commentTable.c.comment_type == -1))
        constructive = conn.execute(constructivesql).fetchall()
      

        # figure out the next and previous essay id
        idSql = db.essayTable.select(db.essayTable.c.assignment_id == assignmentid)
        ids = conn.execute(idSql).fetchall()
        ids = [i[0] for i in ids]
        i = ids.index(int(essayid))
        previousid =  ids[len(ids)-1] if i == 0 else ids[i-1]
        nextid =  nextid = ids[0] if i == len(ids)-1 else ids[i+1]

        sql = db.assignmentTable.select(db.assignmentTable.c.id == assignmentid)
        assignmentTitle = conn.execute(sql).fetchone()['title']
          
        result = env.get_template('adminviewessay.html').render({'row':result_row ,'positive':positive, 'constructive':constructive, 'assignmentid':assignmentid,'assignmentTitle':assignmentTitle, 'previousid':previousid, 'nextid':nextid})
        return result
        
    @cherrypy.expose    
    def admineditassignment(self, oper, assignmentid=None, title=None, description=None, duration=None, bsubmit=None):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()

        conn = request.db
        if oper == 'edit':  
            startdatetime = (datetime.datetime.now().isoformat(' '))[:19]
            sql = db.assignmentTable.update().where(db.assignmentTable.c.id == assignmentid).values({'title':title, 'description':description,'startdatetime':startdatetime, 'duration':duration})
            conn.execute(sql)
        elif oper == 'add': 
            startdatetime = (datetime.datetime.now().isoformat(' '))[:19]
            sql = db.assignmentTable.insert().values({'title':title, 'description':description,'state':'READY','startdatetime':startdatetime, 'duration':duration})
            conn.execute(sql)
        elif oper == 'del': 
            conn.execute("delete from comments where essay_id in (select id from essay where assignment_id = %s)" % (int(assignmentid)))
            conn.execute("delete from essay where assignment_id = %s" % (int(assignmentid)))
            conn.execute("delete from essay_eval where assignment_id = %s" % (int(assignmentid)))
            sql = db.assignmentTable.delete().where(db.assignmentTable.c.id == assignmentid)
            conn.execute(sql)
            
        
        if oper in ['edit','add','del']: 
             raise cherrypy.HTTPRedirect("admin")   
        else:
            if oper == "addnew":
                row = ["new","","","",15]
                oper = 'add'
            elif oper == "toedit":  
                sql = db.assignmentTable.select(db.assignmentTable.c.id == assignmentid)
                row = conn.execute(sql).fetchone()
                oper = 'edit'
            result = env.get_template('admineditassignments.html').render({'id':row[0],'title':row[1],'description':row[2],'duration':row[4],'oper':oper})
            return result
    
    
    def adminchangestate(self, state, assignmentid):
        conn = request.db
        state = state.upper()
        message = "Updated assignment"
        busy = False
        if state == 'BUSY':
            sql = db.assignmentTable.select(or_(db.assignmentTable.c.state == 'BUSY',db.assignmentTable.c.state == 'MARKING'))
            r = conn.execute(sql).fetchall()
            if(len(r) != 0):
                message = "Only one assignment can be active at any time"
                busy = True
  
        if state == 'MARKING':
            esql = db.essayEvalTable.delete(db.essayEvalTable.c.assignment_id == assignmentid)
            e = conn.execute(esql)
            esql = db.essayTable.select(db.essayTable.c.assignment_id == assignmentid)
            e = conn.execute(esql)
            essays = conn.execute(esql).fetchall()
            repetitions = MARKINGREPETITIONS
            N =  len(essays)
            maxCombinations = math.factorial(N)/math.factorial(N-2)/math.factorial(2)
            if maxCombinations< N*repetitions:
                 repetitions = int(math.floor(maxCombinations / N))
            if repetitions >= 1:
                pairs = self.assignPairs(N, repetitions)
                for i in range(N):
                    for j in range(repetitions):
                        student_name = essays[i]['student_name']
                        index = i*repetitions+j
                        essay1 = essays[pairs[index][0]]['id']
                        essay2 = essays[pairs[index][1]]['id']
                        esql = db.essayEvalTable.insert().values({'assignment_id':assignmentid, 'student_name':student_name ,'essay1_id':essay1, 'essay2_id':essay2})
                        conn.execute(esql)
        
        if state == "COMPLETED":
            esql = db.essayEvalTable.select(and_(db.essayEvalTable.c.assignment_id == assignmentid, or_(db.essayEvalTable.c.score1 == None,db.essayEvalTable.c.score2 == None)))
            e = conn.execute(esql).fetchall()
            if(len(e)>0):
                 message = "Not all students finished marking : click on VIEW to see which students are still outstanding"
                 busy = True # prevent transition to the next state
            else:             
                esql = "select id from essay where assignment_id = %s order by id" % (int(assignmentid)) #db.essayTable.select(db.essayTable.c.assignment_id == assignmentid)
                e = conn.execute(esql)
                essays = conn.execute(esql).fetchall()
                ids = [i['id'] for i in essays]

                esql = db.essayEvalTable.select(db.essayEvalTable.c.assignment_id == assignmentid)
                e = conn.execute(esql).fetchall()
                A = numpy.matrix(numpy.zeros((len(ids),len(ids))))

                for i in e:
                    print i
                    row = ids.index(i['essay1_id'])
                    col = ids.index(i['essay2_id']) 
                    s1 = i['score1'] 
                    s2 = i['score2']
                    if s1 == None: s1 = 0.5
                    if s2 == None: s2 = 0.5
                    A[row,col] = s2
                    A[col,row] = s1
                c = scoring.colley(A)
                c1 = scoring.standardize(c)
                for i,id in enumerate(ids):
                    sql = db.essayTable.update().where(db.essayTable.c.id == id).values({'score': float(c1[i]), 'grade':None})
                    conn.execute(sql)   
                

        if not busy:        
            startdatetime = (datetime.datetime.now().isoformat(' '))[:19]
            sql = db.assignmentTable.update().where(db.assignmentTable.c.id == assignmentid).values({'state':state,'startdatetime':startdatetime})
            conn.execute(sql)


        return message

    @cherrypy.expose    
    def adminopassignment(self, assignmentid,oper):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()
        if oper=='busy':
            message = self.adminchangestate('BUSY',assignmentid)
        if oper=='ready':
            message = self.adminchangestate('READY',assignmentid)
        if oper=='marking':
            message = self.adminchangestate('MARKING',assignmentid)
        if oper=='complete':
            message = self.adminchangestate('COMPLETED',assignmentid)
        cherrypy.session['message'] =  message
        raise cherrypy.HTTPRedirect("admin") 
            

    def assignPairs(self, essaysCount, numberToSelect):
        result = []
        essayIndex = 0

        while essayIndex < essaysCount:
            numberIndex = 0
            while numberIndex < numberToSelect:
                a = random.randint(0, essaysCount-1)
                b = random.randint(0, essaysCount-1)
                if (a,b) not in result and (b,a) not in result and not a==b and not a==essayIndex and not b==essayIndex:
                    result.append((a,b))
                    numberIndex += 1
            essayIndex += 1
        return result

    @cherrypy.expose    
    def adminsubmitmarks(self, assignmentid, lowgrade, highgrade):
        if cherrypy.session.get('admin',None) == None:
             return env.get_template('adminlogin.html').render()
        conn = request.db
        rowsSql = db.essayTable.select(db.essayTable.c.assignment_id == assignmentid).order_by(desc(db.essayTable.c.score))
        
        rows = conn.execute(rowsSql).fetchall()
        if(len(rows)>0):
            lowscore = self.saferound(rows[len(rows)-1]['score'],2)
            highscore = self.saferound(rows[0]['score'],2)
            highgrade = float(highgrade)
            lowgrade = float(lowgrade)
            
        for row in rows:
            score = float(row['score'])
            if(highscore == lowscore):
                grade = highgrade
            else:    
                grade = (score-lowscore)/(highscore-lowscore)*(highgrade - lowgrade) + lowgrade
            grade = round(grade,0)    
            sql = db.essayTable.update().where(db.essayTable.c.id == row['id']).values({'grade':grade})
            conn.execute(sql)
        
        raise cherrypy.HTTPRedirect("adminessayresults?assignmentid=%s&complete=1" % assignmentid)  
        


def getPasswordHash(conn):
    return conn.execute(db.adminTable.select()).fetchone()['password']
        

    

if __name__=="__main__":
    # load config for global and application
    cherrypy.config.update(khanconf)
    SAEnginePlugin(cherrypy.engine,ESSAY_DB).subscribe()
    cherrypy.tools.db = SATool()
    cherrypy.tree.mount(EnglishEssay(), '/englishessay', config=enlishessayconf)

    cherrypy.engine.start()
    cherrypy.engine.block()
