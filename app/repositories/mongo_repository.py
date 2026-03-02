from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from app.config.settings import settings
import urllib.parse

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class MongoRepository:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.DB_NAME]

        # Connection Test
        try:
            self.client.admin.command('ping')
            logging.info("Pinged your deployment. You successfully connected to MongoDB!")
        except ConnectionFailure as e:
            logging.error(f"Error connecting to MongoDB: {e}")
            raise
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            raise

    # Collections Getters
    @property
    def oauth_tokens(self):
        return self.db["oauth_tokens"]
    
    @property
    def profiles(self):
        return self.db["profiles"]
    
    def create_indexes(self):
        # auth_tokens
        self.oauth_tokens.create_index([("profile_id", 1)], unique = True)
        self.oauth_tokens.create_index([("token", 1)], unique = True)
        self.oauth_tokens.create_index([("is_valid",1)])

        # profiles
        self.profiles.create_index([("ig_user_id", 1)], unique = True)
        self.profiles.create_index([("ig_username", 1)], unique = True)

        logging.info("Indexes created sucessfuly !")

# Global Instance
mongo_repo = MongoRepository()
mongo_repo.create_indexes()