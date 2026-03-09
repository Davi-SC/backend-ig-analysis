from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from app.config.settings import settings

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
        # oauth_tokens
        self.oauth_tokens.create_index([("profile_id", 1)], unique=True)
        self.oauth_tokens.create_index([("long_lived_token", 1)], unique=True)
        self.oauth_tokens.create_index([("is_valid", 1)])

        # profiles
        self.profiles.create_index([("ig_user_id", 1)], unique=True)
        # username NÃO é unique — pode mudar no Instagram e o mesmo usuário
        # pode ter registros de fluxos diferentes (Facebook/Instagram login)
        self.profiles.create_index([("username", 1)])

        logging.info("Indexes created successfully!")


# Global Instance
mongo_repo = MongoRepository()
mongo_repo.create_indexes()