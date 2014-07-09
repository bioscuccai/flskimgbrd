'''
Licensed under the Beerware license agreement.
'''
from flask import Flask, request, session, g, render_template, url_for, flash, redirect, send_from_directory, Markup, escape, abort
import sqlite3
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import Form
from flask_login import login_user, logout_user, login_required, logout_user, LoginManager, current_user
from wtforms import StringField, TextField, TextAreaField, FileField, PasswordField
from wtforms.validators import DataRequired, Length
from PIL import Image
import os.path
import datetime
import re
import math
import imghdr
import hashlib

WTF_CSRF_ENABLED=False
SECRET_KEY="jkjlkjl"


app=Flask(__name__)
app.config.from_object(__name__)
app.config['SQLALCHEMY_DATABASE_URI']="sqlite:///"+os.path.join(os.path.dirname(__name__), "c3.db")
app.config['UPLOAD_FOLDER']=os.path.join(os.path.dirname(__name__), "uploads")
app.config['THREADS_PER_PAGE']=5
app.config['DEFAULT_NAME']="Anonymous"
app.config['THUMB_W']=200
app.config['THUMB_H']=200
app.config['ALLOWED_FILETYPES']=['png', 'jpeg']
app.config['ALLOWED_EXTENSIONS']=['.png', '.jpg']
db=SQLAlchemy(app)
login_manager=LoginManager()
login_manager.init_app(app)

#######################
#######################
class ChangePasswordForm(Form):
	oldpassword=PasswordField('oldpassword')
	password=PasswordField('password')
	password2=PasswordField('password2')
class LoginForm(Form):
	name=TextField('name')
	password=PasswordField('password')
class BoardForm(Form):
	name=TextField('name')
	short_name=TextField('short_name')
class PostForm(Form):
	name=TextField("name", validators=[DataRequired()])
	title=TextField("title", validators=[Length(256)])
	post=TextAreaField("post", validators=[Length(4096)])
	image=FileField("image")
#######################
#######################
class Iuser(db.Model):
	__tablename__="iuser"
	id=db.Column(db.Integer, primary_key=True)
	name=db.Column(db.String(256), unique=True)
	password=db.Column(db.String(256))
	mode=db.Column(db.Integer)
	
	def is_active(self):
		return True
	def is_authenticated(self):
		return True
	def is_anonymous(self):
		return False
	def get_id(self):
		return self.name

class Iboard(db.Model):
	__tablename__="iboard"
	id=db.Column(db.Integer, primary_key=True)
	name=db.Column(db.String(256))
	short_name=db.Column(db.String(256))
	ithreads=db.relationship("Ithread", backref="iboard", lazy="dynamic")
class Ithread(db.Model):
	__tablename__="ithread"
	id=db.Column(db.Integer, primary_key=True)
	iposts=db.relationship("Ipost", backref="ithread", lazy="dynamic")
	iboard_id=db.Column(db.Integer, db.ForeignKey("iboard.id"))
class Ireport(db.Model):
	__tablename__="ireport"
	id=db.Column(db.Integer, primary_key=True)
	severity=db.Column(db.Integer)
	text=db.Column(db.String(1024))
	ipost_id=db.Column(db.Integer, db.ForeignKey("ipost.id"))
	ipost=db.relationship("Ipost")
class Ipost(db.Model):
	__tablename__="ipost"
	id=db.Column(db.Integer, primary_key=True)
	name=db.Column(db.String(256), default="Anonymous")
	title=db.Column(db.String(256))
	post=db.Column(db.String(4096))
	origfile=db.Column(db.String(256), default="")
	time=db.Column(db.DateTime(), default=datetime.datetime.now)
	ithread_id=db.Column(db.Integer, db.ForeignKey("ithread.id"))
	
	def thumbpath(self):
		return os.path.join("/", app.config['UPLOAD_FOLDER'], "thumbs", "%d%s"%(self.id, os.path.splitext(self.origfile)[1]))
	
	def imgpath(self):
		return os.path.join("/", app.config['UPLOAD_FOLDER'], "images", "%d%s"%(self.id, os.path.splitext(self.origfile)[1]))
	
	def quotedpost(self, forceurl=False):
		escaped=Markup.escape(self.post)
		reg=re.compile(r"&gt;&gt;\d+")
		ess=str(escaped)
		for m in set(reg.findall(ess)):
			qn=m.replace("&gt;&gt;","")
			qint=int(qn)
			np=Ipost.query.filter_by(id=qint)
			if np.count()!=0:
				if np.first().ithread==self.ithread and forceurl==False:
					ess=ess.replace(m, "<a href='#%s'>%s</a>"%(qn,m))
				else:
					ess=ess.replace(m, "<a href='/thread/%d#%s'>%s</a>"%(np.first().ithread.id, qn, m))
		##idezes
		u=[]
		for s in ess.split("\n"):
			if s.startswith("&gt;"):
				u.append("<span style='color: green'>"+s+"</span>")
			else:
				u.append(s)
		ess="\n".join(u)
		return Markup(ess.replace("\n", "<br>"))
	
	def imgsize(self):
		img=Image.open(os.path.join(app.config['UPLOAD_FOLDER'], "images", "%d%s"%(self.id, os.path.splitext(self.origfile)[1])))
		w,h=img.size
		return "%dx%d"%(w,h)
	
	def imgfilesize(self):
		return os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], "images", "%d%s"%(self.id, os.path.splitext(self.origfile)[1])))
################
###HELPER#######
################
def makethumb(fn):
	i=Image.open(os.path.join(app.config['UPLOAD_FOLDER'], "images", fn))
	(w,h)=i.size
	ratio=0.5
	if w>=h:
		ratio=float(app.config['THUMB_W'])/float(w)
	else:
		ratio=float(app.config['THUMB_H'])/float(h)
	i.thumbnail((int(w*ratio), int(h*ratio)), Image.ANTIALIAS)
	i.save(os.path.join(app.config['UPLOAD_FOLDER'], "thumbs", fn))
	
def getpage(board_short_name, pn, ps):
	board=Iboard.query.filter_by(short_name=board_short_name).first()
	threads=Ithread.query.filter_by(iboard=board).all()
	#utolso hozzaszolasok
	lp=[]
	for t in threads:
		lp.append(Ipost.query.filter_by(ithread=t).order_by("time desc").first())
	lp.sort(key=lambda x:x.time)
	starts=ps*pn
	ends=ps*(pn+1)
	tl=[t.ithread for t in lp]
	tl.reverse()
	#lapozas
	starts=ps*pn
	ends=min(ps*(pn+1), len(tl))
	if starts>len(tl) or starts>ends:
		abort(404)
	return tl[starts:ends]
######################################
@login_manager.user_loader
def load_user(user_id):
	u=Iuser.query.filter_by(name=user_id).first()
	return u
@app.context_processor
def inject_board():
	return dict(boards=Iboard.query.all(), user=current_user)

@app.route("/")
def index():
	return render_template("index.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
	form=LoginForm()
	if form.validate_on_submit():
		if Iuser.query.filter_by(name=form.name.data, password=hashlib.sha1(form.password.data).hexdigest()).count()==1:
			u=load_user(form.name.data)
			login_user(u)
			return redirect("/admin")
	return render_template("admin/admin_login.html", form=form)


@app.route("/logout")
def logout():
	logout_user()
	return redirect("/login")

@app.route("/addboard", methods=['POST'])
@login_required
def addboard():
	form=BoardForm()
	if form.validate_on_submit():
		b=Iboard(name=form.name.data, short_name=form.short_name.data)
		db.session.add(b)
		db.session.commit()
	return redirect("/admin")


@app.route("/")
def hello():
	return "hello"


@app.route("/admin")
@login_required
def admin():
	b=Iboard.query.all()
	form=BoardForm()
	pwform=ChangePasswordForm()
	regform=LoginForm()
	#reports=Ireport.query.all()
	users=Iuser.query.all()
	return render_template("admin/admin.html", boards=b, form=form, pwform=pwform, regform=regform, users=users)

@app.route("/board/<board_name>")
def board(board_name):
	#num_threads, tl=getpage(board_name,0,app.config['THREADS_PER_PAGE'])
	#lap
	curr_page=0
	if request.args.get("p") and request.args.get("p").isnumeric():
		curr_page=int(request.args.get("p"))

	tl=getpage(board_name,curr_page,app.config['THREADS_PER_PAGE'])
	board=Iboard.query.filter_by(short_name=board_name).first()
	if board is None:
		abort(404)
	num_threads=Ithread.query.filter_by(iboard=board).count()
	
	#form
	form=PostForm()
	if session.get("name"):
		form.name.data=session["name"]
	else:
		form.name.data=app.config['DEFAULT_NAME']
	
	num_pages=int(math.ceil(float(num_threads)/app.config['THREADS_PER_PAGE']))
	return render_template("board.html", form=form, board=board, threads=tl, pages=range(0,num_pages), curr_page=curr_page)

@app.route("/addthread/<board_name>", methods=["POST"])
def addthread(board_name):
	form=PostForm()
	if form.validate_on_submit():
		session["name"]=form.name.data
		board=Iboard.query.filter_by(short_name=board_name).first()
		if board is None:
			abort(404)
		thr=Ithread()
		board.ithreads.append(thr)
		post=Ipost(name=form.name.data, title=form.title.data, post=form.post.data)
		thr.iposts.append(post)
		db.session.commit()
		if form.image.data:
			post.origfile=form.image.data.filename
			fileext=os.path.splitext(post.origfile)[1]
			if fileext not in app.config['ALLOWED_EXTENSIONS']:
				db.session.delete(post)
				db.session.delete(thr)
				db.session.commit()
				abort(404)
			image_path=os.path.join(app.config['UPLOAD_FOLDER'], "images", "%d%s"%(post.id, fileext))
			form.image.data.save(image_path)
			if imghdr.what(image_path) not in app.config['ALLOWED_FILETYPES']:
				db.session.delete(post)
				db.session.delete(thr)
				db.session.commit()
				abort(404)
			makethumb("%d%s"%(post.id, fileext))
			db.session.commit()
	return redirect("/thread/"+str(thr.id))
@app.route("/thread/<int:thread_id>")
def showthread(thread_id):
	form=PostForm()
	if session.get("name"):
		form.name.data=session["name"]
	else:
		form.name.data=app.config['DEFAULT_NAME']
	thr=Ithread.query.filter_by(id=thread_id).first()
	return render_template("thread.html", form=form, thread_id=thread_id, thr=thr)

@app.route("/addpost/<int:thread_id>", methods=["POST"])
def addpost(thread_id):
	form=PostForm()
	if form.validate_on_submit():
		session["name"]=form.name.data
		thr=Ithread.query.filter_by(id=thread_id).first()
		if thr is None:
			abort(404)
		post=Ipost(name=form.name.data, title=form.title.data, post=form.post.data)
		thr.iposts.append(post)
		db.session.commit()
		#ures
		if form.image.data:
			post.origfile=form.image.data.filename
			fileext=os.path.splitext(post.origfile)[1]
			if fileext not in app.config['ALLOWED_EXTENSIONS']:
				db.session.delete(post)
				db.session.commit()
				flash("allowed extensions are: %s"%" ".join(app.config['ALLOWED_EXTENSIONS']))
				return redirect("/thread/%d"%thread_id)
			image_path=os.path.join(app.config['UPLOAD_FOLDER'], "images", "%d%s"%(post.id, fileext))
			form.image.data.save(image_path)
			if imghdr.what(image_path) not in app.config['ALLOWED_FILETYPES']:
				db.session.delete(post)
				db.session.commit()
				flash("malformed file")
				return redirect("/thread/%d"%thread_id)
			makethumb("%d%s"%(post.id, fileext))
			db.session.commit()
	return redirect("/thread/%d#%d"%(thread_id,post.id))

@app.route("/uploads/<path:p>")
def upl(p):
	return send_from_directory(app.config['UPLOAD_FOLDER'], p)

########
###ADMIN
########
@app.route("/delete_post/<int:p>")
@login_required
def delete_post(p):
	post=Ipost.query.get(p)
	thread=post.ithread.id
	db.session.delete(post)
	db.session.commit()
	return redirect("/thread/%d"%thread)

@app.route("/delete_thread/<int:p>")
@login_required
def delete_thread(p):
	thread=Ithread.query.filter_by(id=p).first()
	board_name=thread.iboard.short_name
	posts=Ipost.query.filter_by(ithread=thread).all()
	for p in posts:
		db.session.delete(p)
	db.session.delete(thread)
	db.session.commit()
	return redirect("/board/"+board_name)

@app.route("/delete_board/<int:p>")
@login_required
def delete_board(p):
	board=Iboard.query.get(p)
	db.session.delete(board)
	db.session.commit()
	return redirect("/admin")

@app.route("/add_user", methods=['POST'])
@login_required
def add_user():
	form=LoginForm()
	if form.validate_on_submit():
		user=Iuser(name=form.name.data, password=hashlib.sha1(form.password.data).hexdigest())
		db.session.add(user)
		db.session.commit()
	return redirect("/admin")

@app.route("/change_password", methods=['POST'])
@login_required
def change_password():
	form=ChangePasswordForm()
	if form.validate_on_submit():
		if form.password.data != form.password2.data:
			flash("passwords don't match")
			return redirect("/admin")
		if current_user!=Iuser.query.filter_by(name=current_user.name, password=hashlib.sha1(form.oldpassword.data).hexdigest()).first():
			flash("old password doesn't match")
			return redirect("/admin")
		current_user.password=hashlib.sha1(form.password.data).hexdigest()
		db.session.commit()
		flash("password changed")
	return redirect("/admin")
if __name__=="__main__":
	app.debug=True
	app.run()
	