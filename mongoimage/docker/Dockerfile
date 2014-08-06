FROM clusterhq/mongolite
MAINTAINER David Gebler <david.gebler@clusterhq.com>
EXPOSE 27017
VOLUME ["/data/db"]
VOLUME ["/data/log"]
RUN touch /home/mongodb/mongo.log
RUN chmod 777 /home/mongodb/mongo.log 
ADD mongo.conf /home/mongodb/mongo.conf
CMD ["/home/mongodb/mongod --config=/home/mongodb/mongo.conf"]
