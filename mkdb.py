from flskimgbrd import db, Iuser
import hashlib
db.create_all()
user=Iuser(name="admin", password=hashlib.sha1("admin").hexdigest())
db.session.add(user)
db.session.commit()