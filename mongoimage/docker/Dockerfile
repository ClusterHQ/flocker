FROM clusterhq/mongolite
MAINTAINER David Gebler <david.gebler@clusterhq.com>
EXPOSE 27017
VOLUME ["/data/db"]
VOLUME ["/data/log"]
#RUN /home/mongodb/mongod --fork --logpath=/home/mongodb/mongo.log
RUN touch /home/mongodb/mongo.log
RUN chmod 777 /home/mongodb/mongo.log 
ADD mongo.conf /home/mongodb/mongo.conf
#RUN /home/mongodb/mongod --config /home/mongodb/mongo.conf
CMD ["/bin/sh"]
CMD ["/home/mongodb/mongod --config=/home/mongodb/mongo.conf"]
