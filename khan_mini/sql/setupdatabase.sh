#mkdir ../db
#--rm ../db/englishessay.db
#sqlite3 ../db/englishessay.db < setupdatabase.sql   
#sqlite3 ../db/englishessay.db < loadsampledata.sql   

mysql -u veesda -p veesda < setupdatabase.sql   
mysql -u veesda -p veesda < loadsampledata.sql   
