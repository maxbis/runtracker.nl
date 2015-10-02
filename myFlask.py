from flask import Flask
from flask import render_template

import requests
import json
import sys
import re,datetime
import pprint


# ---- ---- ---- ----

def findFastestTrack(trackLen, cumTime, cumDistance, heartrate, cadence, moving):
	p1 = 0 #point1 or index1
	p2 = 1 #point2 or index2
	track1 = 0
	track2 = 1
	maxDistance = cumDistance[-1]
	minTime = 99999
	maxLen = len(cumDistance) - 1
	
	if trackLen > maxDistance: # requested subtrack is larger than track
		return(0, 0, 0, 0, 0)
	
	#while maxDistance - cumDistance[p2] > trackLen:
	while p2 < maxLen:
		while ( ( p2 < maxLen ) and (cumDistance[p2] - cumDistance[p1] < trackLen) ):
			p2 = p2 + 1
			
		#print cumDistance[p1], cumDistance[p2], cumDistance[p2]-cumDistance[p1], cumTime[p2]-cumTime[p1]
		thisTime = cumTime[p2] - cumTime[p1]
		if thisTime < minTime:
			minTime = thisTime
			track1 = cumDistance[p1]
			track2 = cumDistance[p2]
			
		p1 = p1 +1

	return(track1, track2, minTime, avgHearRate(heartrate, cumTime, moving, p1, p2), avgHearRate(cadence, cumTime, moving, p1, p2))


def avgHearRate(heartrate, time, move, p1, p2):
		#weighted average: weight is time before and after measurement

		weight = 0
		avgHR = 0

		for i in range (p1, p2):
			if move[i]:
				if i:
					interval = (time[i] - time[i-1])
				else:
					interval = time[i]
				
				weight = weight + interval
				avgHR = avgHR + interval * heartrate[i]

		return(avgHR / weight )


def mmss(seconds):
	string = "%02d:%02d" % divmod(int(seconds+0.5), 60) 
	return( string )
	
    
def analyseActivity(header, id, name, date):
	printDate = datetime.datetime(*map(int, re.split('[^\d]', date)[:-1]))
	url = 'https://www.strava.com/api/v3/activities/'+str(id)+'/streams/time,distance,heartrate,cadence,moving'
	json_data = requests.get(url, headers=header).json()	

	hrZone=[]
	for i in range(len(hrZones)):
		hrZone.append(0)
		
	paceZone=[]
	for i in range(len(paceZones)):
		paceZone.append(0)
		
	cadZone=[]
	for i in range(len(cadZones)):
		cadZone.append(0)
		
	data = {}
	for element in json_data:
		data[element["type"]] = element["data"]
	
	if len(data['time']) != len(data['distance']):
		print "Error: Time data (%d) points do not match distance data points (%d)" % ( len(data['time']), len(data['distance']) )
		sys.exit(1)

	notMoving = 0
	for i in range(0,len(data['moving'])):
		if i:
			dTime = data['time'][i] - data['time'][i-1]
			dDistance = data['distance'][i] - data['distance'][i-1]
		else:
			dTime = data['time'][i]
			dDistance = data['distance'][i]
		
		if dTime <> 0:
			dSpeed = dDistance * 3.6 / dTime
			if (dSpeed < 2): # Speed lower than 2 km/h
				notMoving = notMoving + dTime
		else:
			if not data['moving'][i]:
				notMoving = notMoving + dTime
			
	tRunName = name + " - " + str(printDate) + " - " + "(Strava-id: " + str(id) +")"
	tTotTrackLen = "%3.1f" % ( data['distance'][-1]/1000 )
	tTotTime = "%s (Pause: %s, Moving: %s)" % ( mmss(data['time'][-1]), mmss(notMoving), mmss(data['time'][-1] - notMoving ) )
	tTotPace = 	"%s (%2.2f km/h)" % ( mmss( (data['time'][-1]-notMoving) *1000/data['distance'][-1] ), 3600 / ( (data['time'][-1]-notMoving) *1000/data['distance'][-1]) )
	tAvgHeartrate = "%3s (max %3s)" % ( ( avgHearRate(data['heartrate'], data['time'], data['moving'], 0, len(data['heartrate'])-1 )     ), ( max(data['heartrate']) )   )
	tAvgCadence = "%3s (max %3s)" % ( ( avgHearRate(data['cadence'], data['time'], data['moving'], 0, len(data['cadence'])-1   ) * 2 ), ( max(data['cadence']) * 2 ) )

	trackList=[]
	for trackLen in [ 100, 400, 1000, 1600, 3000, 5000, 6437, 10000, 16093]:
		(track1, track2, minTime, avgHRTrack, avgCad) = findFastestTrack(trackLen, data['time'], data['distance'], data['heartrate'], data['cadence'], data['moving'])
		if minTime <> 0: # if requested subtrack does not exceed track length
			pace = mmss(int((minTime*1000)/(track2-track1)+0.5))
			#print "%5d m. Pace %s (%5.2f km/h) at %5.2f - %5.2f (%7.2f m) in %s s. HR %d Cad %d" % (trackLen, mmss(int((minTime*1000)/(track2-track1)+0.5)), (track2 - track1)*3.6/minTime, track1/1000, track2/1000, (track2-track1), mmss(minTime), avgHRTrack, avgCad*2)
			p1 = int((track1/data['distance'][-1]*100)+0.5)
			p2 = int((track2/data['distance'][-1]*100)+0.5)
		
			trackList.append({ 'tracklen': trackLen, 'p1': p1, 'p2': p2-p1, 'pace': mmss(int((minTime*1000)/(track2-track1)+0.5)), 'mintime': minTime, 'avghr': avgHRTrack, 'avgcad': avgCad*2 })

	for i in range( 1, len(data['time'])-1 ):
		dDistance = data['distance'][i] - data['distance'][i-1]
		if dDistance == 0:
			continue		
		dTime = data['time'][i] - data['time'][i-1]
		dSpeed = dDistance * 3.6 / dTime # speed for this interval in km/h
		dPace = 3600 / dSpeed             # pace for this interval (delta)
	
		for j in reversed(range(len(paceZones))):
			if dPace > paceZones[j]: # if pace in this interval belongs to this zone
				paceZone[j] = paceZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(hrZones))): # for i in [6, 5, 4,...]
			if data['heartrate'][i] > hrZones[j]: # if heart rate in this interval belongs to this zone
				hrZone[j] = hrZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(cadZones))):
			if data['cadence'][i] * 2 > cadZones[j]: # if steps per minute (=cadence*2) in this interval belongs to this zone
				cadZone[j] = cadZone[j] + dTime # count seconds in this zone
				break
				
	#TODO Perc. for graph maximum pn 75% (there's no more place in the table)	
	myPaceZones = paceZones + [600]
	tPaceZones = []
	for i in (range(len(paceZones))):
		highLight = 0
		timePrc = float(paceZone[i]*100)/(data['time'][-1]-notMoving)+0.5 
		if i == 0:
			nextTimePrc = float(paceZone[i+1]*100)/(data['time'][-1]-notMoving)+0.5
			if timePrc >= 10 or nextTimePrc >=10:
				highLight = 1
		if i == 1 and timePrc >= 10:
			highLight = 1
			
		tPaceZones.append({ 'hl': highLight, 'i': i, 'z1': "%3s" % mmss(myPaceZones[i]), 'z2': "%3s" % mmss(myPaceZones[i+1]), 'timeprcstr': "%4.1f" % (timePrc), 'timeprc': int(float(paceZone[i]*100)/(data['time'][-1]-notMoving)+0.5), 'timestr': mmss(paceZone[i]) })

	myHrZones = hrZones + [999]
	tHrZones = []
	highLight = 0
	for i in (range(len(hrZones))):
	 	timePrc = float(hrZone[i]*100)/(data['time'][-1]-notMoving ) 
		if i >= 5 and timePrc >= 10:
			highLight = 1
		tHrZones.append({ 'hl': highLight, 'i': i, 'z1': i, 'z2': "%3s-%3s" % (myHrZones[i], myHrZones[i+1]), 'timeprcstr': "%4.1f" % (timePrc), 'timeprc': int(float(hrZone[i]*100)/(data['time'][-1]-notMoving)+0.5), 'timestr': mmss(paceZone[i]) })

	myCadZones = cadZones + [999]
	tCadZones = []
	highLight = 0
	for i in (range(len(cadZones))):
	 	timePrc = float(cadZone[i]*100)/(data['time'][-1]-notMoving ) 
		if i >= 5 and timePrc >= 10:
			highLight = 1
		tCadZones.append({ 'hl': highLight, 'i': i, 'z1': "%3s" % (i), 'z2': "%3s-%3s" % (myCadZones[i], myCadZones[i+1]), 'timeprcstr': "%4.1f" % (timePrc), 'timeprc': int(float(cadZone[i]*100)/(data['time'][-1]-notMoving)+0.5), 'timestr': mmss(cadZone[i]) })

	return( render_template('part2.html', tTrackList=trackList, tPaceZones=tPaceZones, tHrZones=tHrZones, tCadZones=tCadZones, tRunName=tRunName, tTotTrackLen=tTotTrackLen, tTotTime=tTotTime, tTotPace=tTotPace, tAvgHeartrate=tAvgHeartrate, tAvgCadence=tAvgCadence) )


# ---- ---- ---- ----

paceZones= [ 0, 220, 240, 260, 280, 300, 330 ]
hrZones  = [ 0,  95, 114, 133, 152, 171, 190 ]
cadZones = [ 0, 160, 165, 170, 175, 180, 185 ]

# ---- ---- ---- ----

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World - main Index!'

@app.route('/lastrun')
def lastrun():
    return 'Hello World'

@app.route('/graph')
def graph():

	header = {'Authorization': 'Bearer 11bb67157265292117578cea5b453da4435c6235'}
	url = 'https://www.strava.com/api/v3/athlete/activities/?per_page=6'

	HTML = render_template('part1.html')
	json_data = requests.get(url, headers=header).json()
	
	for item in json_data:
		if item['type'] == 'Run':
			activityId =  item['id']
			activityName = item['name']
			activityDate = item['start_date_local']
			HTML = HTML + analyseActivity(header, activityId, activityName, activityDate) +"<br>"
	
	return( HTML )

if __name__ == '__main__':
    app.run(debug = True)
    
    
