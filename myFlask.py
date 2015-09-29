from flask import Flask
from flask import render_template
from flask import request
from ConfigParser import SafeConfigParser


import requests
import json
import sys
import re,datetime
import pprint
import os.path


# ---- ---- ---- ----

# Find fastest subtrack
def findFastestTrack(trackLen, cumTime, cumDistance, heartrate, cadence):
	p1 = 0 #point1 or index1
	p2 = 1 #point2 or index2
	x = 0  # point 1 fastest track so far
	y = 1  # point 2 fastest track so far
	
	maxDistance = cumDistance[-1]
	minTime = 99999
	maxLen = len(cumDistance) - 1
	
	if trackLen > maxDistance: # requested subtrack is larger than track
		return(0, 0, 0, 0, 0)
	
	#while maxDistance - cumDistance[p2] > trackLen:
	while p2 < maxLen:
		while ( ( p2 < maxLen ) and (cumDistance[p2] - cumDistance[p1] < trackLen) ):
			p2 = p2 + 1
			
		thisTime = cumTime[p2] - cumTime[p1]
		if thisTime < minTime:
			minTime = thisTime
			x = p1
			y = p2
			
		p1 = p1 +1

	return(x, y, minTime, wAvg(heartrate, cumTime, p1, p2), wAvg(cadence, cumTime, x, y))

# Calc weighted average
def wAvg(thisList, time, p1, p2):
		#weighted average: weight is time (delta) before measurement

		thisWeight = 0
		thisAvg = 0

		for i in range (p1, p2):
			if i: 
				interval = (time[i] - time[i-1]) # begin of list so list[i-1] does not exist
			else: 
				interval = time[i] # begin of list so list[i-1] does not exist
			
			thisWeight = thisWeight + interval
			thisAvg = thisAvg + interval * thisList[i]

		return( thisAvg / thisWeight )

# Format integer to mm:ss string
def mmss(seconds):
	# return formatted string mm:ss
	if seconds < 3600:
		string = "%02d:%02d" % divmod(int(seconds+0.5), 60) 
	else:
		hours=0
		while seconds>=3600:
			seconds=seconds-3600
			hours=hours+1
		# TODO print hours and not 1! (issues with formatted string)
		string = "1:%02d:%02d" % ( divmod(int(seconds+0.5), 60) )

	return( string )	
 
# Prepare data for the zone graphs
def getZoneData(thisZones, cumTimeinZone, moveTime, iteration ):
 	thisZonesPlus = thisZones + [999]
	dataZones = []
	highLight = 0
	
	#iteration = (range(len(thisZones)))[::-1]
	last = iteration[-2:]
	
	for i in iteration: # 6, 5, 4
	 	timePrc = float( cumTimeinZone[i]*100.0 / moveTime )
		if (i in last) and timePrc >= 10:
			highLight = 1
			
		dataZones.append({ 'hl': highLight, 'i': i, 'z1mmss': mmss(thisZones[i]), 'z2mmss': (mmss(thisZonesPlus[i+1])), 'z1': thisZones[i], 'z2': thisZonesPlus[i+1], 'timeprcstr': "%4.1f" % (timePrc), 'timeprc': min(78,int((timePrc)+0.5)), 'timestr': mmss(cumTimeinZone[i]) })

	return(dataZones)

# clean data, remove outliers and pauses
def filterData(time, distance, heartrate, cadence, moving ):
	# create new list and filter pauses as well as outliers in speed
	
	outlierL = 2   # min outlier 3 km/h
	outlierR = 25 # max outlier 24 km/h
	
	lTime = []
	lDistance = []
	lSpeed = []
	lHr = []
	lCad = []
	lStep = []
	filtered = []
	filt = {}
	
	start = 0
	while (not moving[start] or not distance[start] or distance[start]*3.6/time[start]<=2 or distance[start]*3.6/time[start]>=25):
		start=start+1
	
	lTime.append( time[start] )
	lDistance.append( distance[start] )
	lHr.append( heartrate[start] )
	lCad.append( cadence[start] )
	
	start = start + 1
		
	for i in range(start, len(time)):
		dDistance = distance[i] - distance[i-1]
		dTime = time[i] - time[i-1]
		if ( dTime>0 and moving[i] ):
			dSpeed = dDistance * 3.6 / dTime # speed for this interval in km/h
			if ( dSpeed > outlierL and dSpeed < outlierR ):
				lTime.append( lTime[-1] + dTime )
				lSpeed.append( dSpeed )
				lDistance.append( lDistance[-1] + dDistance )
				lHr.append( heartrate[i] )
				lCad.append( cadence[i] )
				if cadence[i] > 0:
					#lStep.append( dDistance*100 / (cadence[i]*2*dTime/60) )
					lStep.append( dDistance*3000 / (cadence[i]*dTime) )
				else:
					lStep.append( 0 )
			else:
				filtered.append(i)
				filt[i]=dTime
		else:
			filtered.append(i)
			filt[i]=dTime
				
		# endif no move,skip data point			
	
	return(lTime, lDistance, dSpeed, lHr, lCad, lStep, filtered, filt) 

# init new empty list as big as input list
def initList(list):
	newList = []
	for i in range(len(list)):
		newList.append(0)
	return(newList)
	
# Main routine to start analysing data
def analyseActivity(header, id, name, date):
	printDate = datetime.datetime(*map(int, re.split('[^\d]', date)[:-1]))
	
	jsonFileName = os.path.join("cache", "strava"+str(id)+".json")
	
	if os.path.isfile(jsonFileName):
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		url = 'https://www.strava.com/api/v3/activities/'+str(id)+'/streams/time,distance,heartrate,cadence,moving'
		json_data = requests.get(url, headers=header).json()	
		file = open(jsonFileName,"w")
		json.dump(json_data, file)
		file.close()
	
	hrZone = initList(hrZones)
	paceZone = initList(paceZones)
	cadZone = initList(cadZones)
	stepZone = initList(stepZones)
		
	data = {}
	for element in json_data:
		data[element["type"]] = element["data"]
	
	if 'cadence' not in data.keys():
		data['cadence'] = initList(data['time'])
		
	if 'heartrate' not in data.keys():
		data['heartrate'] = initList(data['time'])

	(lTime,lDistance,lSpeed,lHr,lCad,lStep,filtered,filt) = filterData(data['time'],data['distance'],data['heartrate'],data['cadence'],data['moving'])

	notMoving = data['time'][-1] - lTime[-1]

	tRunName = name
	tRunId = str(id)
	tRunDate = str(printDate).split(' ') #list with date and time
	tTotTrackLen = "%4.2f" % ( lDistance[-1]/1000 )
	tTotTime = "%s (Pause: %s, Moving: %s)" % ( mmss(lTime[-1]+notMoving), mmss(notMoving), mmss(lTime[-1] ) )
	#tTotPace = 	"%s (%2.2f km/h)" % ( mmss( (lTime[-1]) *1000/lDistance[-1] ), 3600 / ( (lTime[-1]) *1000/lDistance[-1]) )
	tTotPace = 	"%s" % ( mmss( (lTime[-1]) *1000/lDistance[-1] ) )
	tAvgHeartrate = "%3s (max %3s)" % ( ( wAvg(lHr, lTime, 0, len(lHr)-1 ) ), ( max(lHr) ) )
	tAvgCadence = "%3s (max %3s)" %   ( ( wAvg(lCad, lTime, 0, len(lCad)-1 )*2 ), ( max(lCad) * 2 ) )
	tAvgStep = "%2.2f (max %2.2f)" %  ( ( wAvg(lStep, lTime, 0, len(lStep)-1 ) ), ( max(lStep) ) )


	trackList=[]
	for trackLen in [ 100, 400, 800, 1000, 1600, 3000, 5000, 6000, 6437, 10000, 16093, 21098]:
		(x, y, minTime, avgHRTrack, avgCad) = findFastestTrack(trackLen, lTime, lDistance, lHr, lCad )
		if minTime <> 0: # if requested subtrack does not exceed track length
			pace = mmss(int((minTime*1000)/(lDistance[y]-lDistance[x])+0.5))
			p1 = int((lDistance[x]/lDistance[-1]*100)+0.5) # percentage begin track
			p2 = int((lDistance[y]/lDistance[-1]*100)+0.5) # percentage end track

			sumFlt=0
			numFlt=0
			# filt is dictionary[index, seconds] with indexes referring to the sequence of the main data set
			# just before the point filtered; seconds contains the filtered #seconds.
			for key in ({ k:v for (k,v) in filt.items() if (k>=x and k<=y) }):
				sumFlt=sumFlt+filt[key]
				numFlt=numFlt+1
		
			trackList.append({ 'tracklen': trackLen, 'p1': p1, 'p2': p2-p1, 'pace': pace, 'mintime': mmss(minTime), 'avghr': avgHRTrack, 'minhr': min(lHr[x:y]), 'maxhr': max(lHr[x:y]), 'avgcad': avgCad*2, 'filtered': sumFlt })

	for i in range( 1, len(lTime)-1 ):
		dTime = lTime[i] - lTime[i-1]
		dDistance = lDistance[i] - lDistance[i-1]
		dSpeed = dDistance * 3.6 / dTime # speed for this interval in km/h		
		dPace = 3600 / dSpeed             # pace for this interval (delta)
			
		for j in reversed(range(len(paceZones))):
			if dPace > paceZones[j]: # if pace in this interval belongs to this zone
				paceZone[j] = paceZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(hrZones))): # for i in [6, 5, 4,...]
			if lHr[i] > hrZones[j]: # if heart rate in this interval belongs to this zone
				hrZone[j] = hrZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(cadZones))):
			if lCad[i] * 2 > cadZones[j]: # if steps per minute (=cadence*2) in this interval belongs to this zone
				cadZone[j] = cadZone[j] + dTime # count seconds in this zone
				break
		for j in reversed(range(len(stepZones))):
			if lStep[i] > stepZones[j]: # if steps per minute (=cadence*2) in this interval belongs to this zone
				stepZone[j] = stepZone[j] + dTime # count seconds in this zone
				break		
		
	tPaceZones = getZoneData(paceZones, paceZone, lTime[-1], range(len(paceZones))[::-1] )
	tHrZones =( getZoneData(hrZones, hrZone, lTime[-1], range(len(hrZones)) ) )
	tCadZones =( getZoneData(cadZones, cadZone, lTime[-1], range(len(cadZones)) ) )
	tStepZones =( getZoneData(stepZones, stepZone, lTime[-1], range(len(stepZones)) ) )
	
	# Split time / hTimes
	interval = int((lDistance[-1]/2)+0.5)
	hSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)

	# Qsplits
	interval = int((lDistance[-1]/4)+0.5)
	qSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)
	
	# kmsplits
	interval = 1000
	kmSpeed = avgSpeedperTrack(lDistance, lTime, interval, lHr)

	return( render_template('part2.html', tTrackList=trackList, tPaceZones=tPaceZones, tHrZones=tHrZones, tCadZones=tCadZones, tStepZones=tStepZones, tRunName=tRunName, tRunId = tRunId, tRunDate=tRunDate, tTotTrackLen=tTotTrackLen, tTotTime=tTotTime, tTotPace=tTotPace, tAvgHeartrate=tAvgHeartrate, tAvgCadence=tAvgCadence, tAvgStep=tAvgStep, hSpeed=hSpeed, qSpeed=qSpeed, kmSpeed=kmSpeed ) )

# Determine average speed per x meter
def avgSpeedperTrack(distance, time, interval, hr):

	thisInterval = 1
	prev = 0
	iSpeed = []
	iTime = []
	avgSpeed = 1000*time[-1]/distance[-1]
	
	for i in range(len(distance)):
		if distance[i] > (thisInterval * interval):
			if prev:
				dTime = time[i] - time[prev]
				dDistance = distance[i] - distance[prev]
			else:
				dTime = time[i]
				dDistance = distance[i]
				
			dSpeed = 1000*dTime/dDistance
			iHr = wAvg(hr, time, prev, i)

			iSpeed.append( { 'i': thisInterval, 'dDistance': int(dDistance+0.5), 'dTime': dTime, 'dSpeed': dSpeed, 'dTimeStr': mmss(dTime), 'dSpeedStr': mmss(dSpeed), 'faster': (dSpeed<=avgSpeed), 'hr': iHr, 'hi_low': 0 } )

			prev = i
			thisInterval = thisInterval + 1
	
	
	dTime = time[i] - time[prev]
	if dTime:
		dDistance = distance[i] - distance[prev]
		dSpeed = 1000*dTime/dDistance
		iHr = wAvg(hr, time, prev, i)

		iSpeed.append( { 'i': thisInterval, 'dDistance': int(dDistance+0.5), 'dTime': dTime, 'dSpeed': dSpeed, 'dTimeStr': mmss(dTime), 'dSpeedStr': mmss(dSpeed), 'faster': (dSpeed<=avgSpeed), 'hr': iHr, 'hi_low': 0 } )
	
	low, hi, lowi, hii = 999, 0, 0, 0
	
	for i in range(len(iSpeed)):
		if iSpeed[i]['dSpeed'] < low:
			low = iSpeed[i]['dSpeed']
			lowi = i
		if iSpeed[i]['dSpeed'] > hi:
			hi = iSpeed[i]['dSpeed']
			hii= i
	
	iSpeed[lowi]['hi_low'] = -1
	iSpeed[hii]['hi_low'] = 1
	
	return (iSpeed)
			


# ---- ---- ---- ----

paceZones= [ 0, 220, 240, 260, 280, 300, 330 ]
hrZones  = [ 0,  95, 114, 133, 152, 171, 190 ]
cadZones = [ 0, 140, 150, 155, 160, 165, 170, 175, 180, 185 ]
stepZones= [ 0, 100, 110, 120, 130, 140, 150, 160, 170, 180 ]

# ---- ---- ---- ----

parser = SafeConfigParser()
parser.read('auth.ini')
bearer_id = parser.get('strava', 'bearer_id')

header = {'Authorization': 'Bearer {0}'.format(bearer_id)}
 
# ---- ---- ---- ----

app = Flask(__name__)

@app.route('/')
def hello_world():
    return(list())


@app.route('/lastrun')
def lastrun():
    return 'Hello World'


@app.route('/strava')
def strava():
	activityId = 0
	activityId =  request.args['id']
	
	url = 'https://www.strava.com/api/v3/activities/'+str(activityId)
	HTML = render_template('part1.html')

	jsonFileName = os.path.join("cache", "activty"+str(activityId)+".json")
	
	if os.path.isfile(jsonFileName):
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		json_data = requests.get(url, headers=header).json()
		file = open(jsonFileName,"w")
		json.dump(json_data, file)
		file.close()

	activityName = json_data['name']
	activityDate = json_data['start_date_local']
	HTML = HTML + analyseActivity(header, activityId, activityName, activityDate) +"<br>"
	return( "<html>" + HTML + "</html>" )
	

@app.route('/last')
def last():

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
	
@app.route('/list')
def list():

	readCache = 0
	#readCache =  request.args['refresh']

	weekday = ['Mo','Tu','We','Th','Fr','Sa','Su']

	url = 'https://www.strava.com/api/v3/athlete/activities/?per_page=30'

	HTML = render_template('part1.html')

	jsonFileName = os.path.join("cache", "list.json")
	
	if os.path.isfile(jsonFileName) and readCache:
		file = open(jsonFileName, "r")
		json_data = json.load(file)
		file.close()
	else:
		json_data = requests.get(url, headers=header).json()
		file = open(jsonFileName,"w")
		json.dump(json_data, file)
		file.close()
	
	for item in json_data:
		if item['type'] == 'Run':
			
			runDate = datetime.datetime(*map(int, re.split('[^\d]', item['start_date_local'])[:-1]))
			tWeekDay = weekday[runDate.weekday()]
			tRunDate = runDate.strftime("%d %b, %H:%M")
			tRunPace = mmss(1000/item['average_speed'])
			tDistance = "%3.1f" % ( item['distance']/1000 )
			tMovingTime = mmss(item['moving_time'])
			
			HTML = HTML + render_template('list.html', item=item, tRunDate=tRunDate, tRunPace=tRunPace, tDistance=tDistance, tWeekDay=tWeekDay, tMovingTime=tMovingTime)
	
	return( "<html>" + HTML + "</html>" )

if __name__ == '__main__':
 	app.run(host='0.0.0.0', port=8080)
    
    
