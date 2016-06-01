import logging
from telegram import Emoji, ForceReply, KeyboardButton, \
    ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, \
    CallbackQueryHandler, Filters
import json, requests, urllib
from urllib import parse, request
from googleapiclient.discovery import build
from datetime import datetime, timedelta

# Important Values for the Bot
NAME = "Voter_Help_Bot"
BOT_KEY = "186316316:AAHeir7pHkLnwxEtw1Yn6M5Scac02iJIZOk"
GET_ADDRESS, GET_CITY, GET_STATE, GET_ZIP, AWAIT_REGISTRATION, FINISHED, REMINDER_MODE = range(7)
apiKey = "AIzaSyBeXcLqyIOqZkIMqGBVJmVLikBkC5QHh6c"
searchEngineKey = '006560762859714176178:dkkf_njhddu'


# States are saved in a dict that maps chat_id -> state
state = dict()
# Temporary storage for data while gathering info
context = dict()
# Important info about a user that the bot will store by mapping user_id >- info
#This is info that the bot will refer back to in the future
state_of_residence = dict()
addresses = dict()
electionAddress = dict()
electionDate = dict()
notificationsEnabled = dict()

#Command listener that begins a message chain to gather information from user
def get_address(bot, update):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    user_state = state.get(user_id, GET_ADDRESS)

    state[user_id] = GET_CITY# set the state
    bot.sendMessage(chat_id,
                        text="Please type in your house number and street",
                        reply_markup=ForceReply())

#Message listener that changes depending on how much information
#the user has given the bot so far
def bot_setup(bot, update):
    #Gather relevant message data
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    text = update.message.text
    chat_state = state.get(chat_id, GET_ADDRESS)

    #Prompt user for their city
    if chat_state == GET_CITY:
        state[chat_id] = GET_STATE
        # Save the user id and the answer to context
        context[chat_id] = update.message.text
        bot.sendMessage(chat_id, text="Now enter your City",
                        reply_markup= ForceReply())

    #Prompt user for their state
    elif chat_state == GET_STATE:
        context[chat_id] = context[chat_id] + ", " + text
        state[chat_id] = GET_ZIP
        bot.sendMessage(chat_id, text= "Now enter your State of Residence",
                        reply_markup= ForceReply())
    #Prompt user for their zipcode
    elif chat_state == GET_ZIP:
        state_of_residence[user_id] = text
        context[chat_id] = context[chat_id] + ", " + text
        state[chat_id] = AWAIT_REGISTRATION
        bot.sendMessage(chat_id, text="Now enter your Zip Code",
                        reply_markup= ForceReply())
    #Prompt user to register to vote
    elif chat_state == AWAIT_REGISTRATION:
        addresses[user_id] = context[chat_id] + " " + text
        del context[chat_id]
        state[chat_id] = FINISHED
        register_to_vote_markup = ReplyKeyboardMarkup([[KeyboardButton("Done Registering")]],
                                  one_time_keyboard = True)
        bot.sendMessage(chat_id, text="Click this link: "
                        + googleSearch('Register to Vote in %s'
                        % state_of_residence[user_id]) + " to register to vote!",
                        reply_markup= register_to_vote_markup)

    #Give the user valuable information about the upcoming election if there is one
    elif chat_state == FINISHED:
        electionDta = findVoterInfo(addresses[user_id])
        #Try giving the user election information based on their provided information
        try:
            state[chat_id] = REMINDER_MODE
            notificationsEnabled[chat_id] = True
            loc = electionDta['pollingLocations'][0]['address']
            electionAddress[user_id] = (loc['line1'] + ', ' + loc['city'] + ', '
                                        + loc['state'] + ' ' + loc['zip'])
            electionDate[user_id] = electionDta['election']['electionDay']
            election_date_object = datetime.strptime(electionDate[user_id], '%Y-%m-%d')
            responseText = 'You are done! Your polling location is: %s.' \
                            ' Your election date is: %s I will send you a ' \
                            'reminder every few days!' % (electionAddress[user_id],
                                                          electionDate[user_id])
            info_markup = ReplyKeyboardMarkup([[KeyboardButton("Election Info"),
                                                KeyboardButton("Disable Notifications"),
                                                KeyboardButton("Enable Notifications")]],
                                                one_time_keyboard = False)
            bot.sendMessage(chat_id, text= responseText, reply_markup = info_markup)
            #Function that will keep sending reminders to user
            def constantReminderFunction(bot):
                reminderText = 'Do not forget to vote! Your polling location' \
                                ' is: %s. Your election date is: %s.' \
                                ' I will continue to send you a reminder every' \
                                ' few days!' % (electionAddress[user_id],
                                                electionDate[user_id])
                if (notificationsEnabled[chat_id]):
                    bot.sendMessage(chat_id, text= reminderText)
                now = datetime.now()
                timeDiff = election_date_object - now
                if timeDiff.total_seconds() > 60 * 60 * 24 * 3:
                    job_queue.put(constantReminderFunction,
                                  60 * 60 * 24 * 3, repeat=False)
            #Function that will send reminder to user the day before the election
            def lastReminderFunction(bot):
                reminderText = 'Do not forget to vote tomorrow! Your polling ' \
                                'location is: %s. This will be' \
                                ' my last reminder!' % (electionAddress[user_id])
                bot.sendMessage(chat_id, text= reminderText)
            now = datetime.now()
            timeDiff = election_date_object - now
            #Add the reminders to the job que
            job_queue.put(constantReminderFunction, 60 * 60 * 24 * 3, repeat=False)
            job_queue.put(constantReminderFunction, timeDiff.total_seconds()
                          - (60 * 60 * 24), repeat=False)
        #Handle Errors when the GET Request does not execute properly
        except (KeyError):
            error = electionDta['error']['message']
            if error == 'Failed to parse address':
                bot.sendMessage(chat_id, text="Invalid Address, use /set to try again")
            else:
                bot.sendMessage(chat_id, text='You have no elections coming up! ' \
                                'Make sure to check back and keep up with the ' \
                                'news to vote in the future')
    elif chat_state == REMINDER_MODE:
        if text == "Disable Notifications":
            notificationsEnabled[chat_id] = False
            bot.sendMessage(chat_id, text= 'Notifications Disabled. '\
                            'You will not receive a notification after your next one')
        elif text == "Enable Notifications":
            notificationsEnabled[chat_id] = True
            bot.sendMessage(chat_id, text= "Notifications Enabled")
        elif text == "Election Info":
            infotext = 'Your polling location is: %s Your election date ' \
                        'is: %s' % (electionAddress[user_id],electionDate[user_id])
            bot.sendMessage(chat_id, text= infotext)

#Method that uses the Google Custom Search API to search a query
def googleSearch(searchQuery):
    service = build("customsearch", "v1",
            developerKey=apiKey)
    res = service.cse().list(q= searchQuery,
                             cx= searchEngineKey,).execute()
    topResult = res['items'][0]
    topResultURL = topResult['formattedUrl']
    return topResultURL
#Method that finds voter info using the Google Civic Info API based on Address
def findVoterInfo(address):
    url = "https://www.googleapis.com/civicinfo/v2/voterinfo?address=%s&key=%s" % (address, apiKey)
    electionData = requests.get(url).json()
    return electionData

#Command listener for the help command that assists a user in getting started
def help(bot, update):
    bot.sendMessage(update.message.chat_id,
                    text= "Hi, Type /set to reset the bot and get reminded to vote!")
#Command listener for the start command which begins the bot.
def start(bot, update):
    bot.sendMessage(update.message.chat_id,
                    text= 'Hi, I am VoterBot, here to ensure you do not forget'\
                     ' to vote on time! Type /set to begin!')

#Error listener that logs errors
def error(bot, update, error):
    logging.warning('Update "%s" caused error "%s"' % (update, error))

#Main method that starts the bot
def main():
# Create the Updater and pass it your bot's token.
    #Create the bot
    global job_queue
    updater = Updater(BOT_KEY)
    job_queue = updater.job_queue
    # The command
    updater.dispatcher.add_handler(CommandHandler('set', get_address))
    # The answer
    updater.dispatcher.add_handler(MessageHandler([Filters.text], bot_setup))
    # The confirmation
    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_handler(CommandHandler('help', help))
    updater.dispatcher.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()

if __name__ == '__main__':
    main()
