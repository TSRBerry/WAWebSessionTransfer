import json
import logging
import os
import platform
import time
from enum import Enum
from typing import Union, NoReturn, Optional

import selenium.webdriver.chrome.options as c_op
import selenium.webdriver.chrome.webdriver as c_wd
import selenium.webdriver.firefox.options as f_op
import selenium.webdriver.firefox.webdriver as f_wd
from selenium import webdriver
from selenium.common.exceptions import WebDriverException


class Browser(Enum):
    CHROME = 1
    FIREFOX = 2


class SessionHandler:
    __URL = 'https://web.whatsapp.com/'
    __browser_choice = 0
    __log_level: int
    __browser_user_dir: str
    __browser_profile_list: list[str]
    __browser_options: Union[c_op.Options, f_op.Options]
    __driver: Union[c_wd.WebDriver, f_wd.WebDriver]
    log: logging.Logger

    @staticmethod
    def verify_profile_object(profile_obj: list[dict[str, str]]) -> bool:
        for entry in profile_obj:
            if 'key' in entry.keys() and 'WASecretBundle' in entry['key']:
                return True
        return False

    @staticmethod
    def convert_ls_to_idb_obj(ls_obj: dict[str, str]) -> list[dict[str, str]]:
        idb_list = []
        for ls_key, ls_val in ls_obj:
            idb_list.append({'key': ls_key, 'value': ls_val})
        return idb_list

    @staticmethod
    def convert_idb_to_ls_obj(idb_obj: list[dict[str, str]]) -> dict[str, str]:
        ls_dict = {}
        for idb_entry in idb_obj:
            ls_dict[idb_entry['key']] = idb_entry['value']
        return ls_dict

    def __refresh_profile_list(self) -> NoReturn:
        self.log.debug('Getting browser profiles...')
        if self.__browser_choice == Browser.CHROME:
            self.__browser_profile_list = ['']
            for profile_dir in os.listdir(self.__browser_user_dir):
                if 'profile' in profile_dir.lower():
                    if profile_dir != 'System Profile':
                        self.__browser_profile_list.append(profile_dir)
        elif self.__browser_choice == Browser.FIREFOX:
            # TODO: consider reading out the profiles.ini
            self.__browser_profile_list = []
            for profile_dir in os.listdir(self.__browser_user_dir):
                if not profile_dir.endswith('.default'):
                    if os.path.isdir(os.path.join(self.__browser_user_dir, profile_dir)):
                        self.__browser_profile_list.append(profile_dir)

        self.log.debug('Browser profiles registered.')

    def __init_browser(self) -> NoReturn:
        self.log.debug("Setting browser user dirs...")
        if self.__browser_choice == Browser.CHROME:
            self.__browser_options = webdriver.ChromeOptions()

            if self.__platform == 'windows':
                self.__browser_user_dir = os.path.join(os.environ['USERPROFILE'],
                                                       'Appdata', 'Local', 'Google', 'Chrome', 'User Data')
            elif self.__platform == 'linux':
                self.__browser_user_dir = os.path.join(os.environ['HOME'], '.config', 'google-chrome')

        elif self.__browser_choice == Browser.FIREFOX:
            self.__browser_options = webdriver.FirefoxOptions()

            if self.__platform == 'windows':
                self.__browser_user_dir = os.path.join(os.environ['APPDATA'], 'Mozilla', 'Firefox', 'Profiles')
                self.__browser_profile_list = os.listdir(self.__browser_user_dir)
            elif self.__platform == 'linux':
                self.__browser_user_dir = os.path.join(os.environ['HOME'], '.mozilla', 'firefox')

        self.log.debug('Browser user dirs set.')

        self.__browser_options.headless = True
        self.__refresh_profile_list()

    def __get_local_storage(self) -> dict[str, str]:
        self.log.debug('Executing getLS function...')
        return self.__driver.execute_script('''
        var waSession = {};
        waLs = window.localStorage;
        for (int i = 0; i < waLs.length; i++) {
            waSession[waLs.key(i)] = waLs.getItem(waLs.key(i));
        }
        return waSession;
        ''')

    def __set_local_storage(self, wa_session_obj: dict[str, str]) -> NoReturn:
        for ls_key, ls_val in wa_session_obj.items():
            self.__driver.execute_script('window.localStorage.setItem(arguments[0], arguments[1]);',
                                         ls_key, ls_val)

    def __get_indexed_db_user(self) -> list[dict[str, str]]:
        self.log.debug('Executing getIDBObjects function...')
        self.__driver.execute_script('''
        window.waScript = {};
        window.waScript.waSession = undefined;
        function getAllObjects() {
            window.waScript.dbName = "wawc";
            window.waScript.osName = "user";
            window.waScript.db = undefined;
            window.waScript.transaction = undefined;
            window.waScript.objectStore = undefined;
            window.waScript.getAllRequest = undefined;
            window.waScript.request = indexedDB.open(window.waScript.dbName);
            window.waScript.request.onsuccess = function(event) {
                window.waScript.db = event.target.result;
                window.waScript.transaction = window.waScript.db.transaction(window.waScript.osName);
                window.waScript.objectStore = window.waScript.transaction.objectStore(window.waScript.osName);
                window.waScript.getAllRequest = window.waScript.objectStore.getAll();
                window.waScript.getAllRequest.onsuccess = function(getAllEvent) {
                    window.waScript.waSession = getAllEvent.target.result;
                };
            };
        }
        getAllObjects();
        ''')
        self.log.debug('Waiting until IDB operation finished...')
        while not self.__driver.execute_script('return window.waScript.waSession != undefined;'):
            time.sleep(1)
        self.log.debug('Getting IDB results...')
        wa_session_obj: list[dict[str, str]] = self.__driver.execute_script('return window.waScript.waSession;')
        # self.log.debug('Got IDB data: %s', wa_session_obj)
        return wa_session_obj

    def __set_indexed_db_user(self, wa_session_obj: list[dict[str, str]]) -> NoReturn:
        self.log.debug('Inserting setIDBObjects function...')
        # TODO: If I support loading multiple sessions in one browser window I only need to execute this once.
        self.__driver.execute_script('''
        window.waScript = {};
        window.waScript.insertDone = 0;
        window.waScript.jsonObj = undefined;
        window.waScript.setAllObjects = function (_jsonObj) {
            window.waScript.jsonObj = _jsonObj;
            window.waScript.dbName = "wawc";
            window.waScript.osName = "user";
            window.waScript.db;
            window.waScript.transaction;
            window.waScript.objectStore;
            window.waScript.clearRequest;
            window.waScript.addRequest;
            window.waScript.request = indexedDB.open(window.waScript.dbName);
            window.waScript.request.onsuccess = function(event) {
                window.waScript.db = event.target.result;
                window.waScript.transaction = window.waScript.db.transaction(window.waScript.osName, "readwrite");
                window.waScript.objectStore = window.waScript.transaction.objectStore(window.waScript.osName);
                window.waScript.clearRequest = window.waScript.objectStore.clear();
                window.waScript.clearRequest.onsuccess = function(clearEvent) {
                    for (var i=0; i<window.waScript.jsonObj.length; i++) {
                        window.waScript.addRequest = window.waScript.objectStore.add(window.waScript.jsonObj[i]);
                        window.waScript.addRequest.onsuccess = function(addEvent) {
                            window.waScript.insertDone++;
                        };
                    }
                };
            };
        }
        ''')
        self.log.debug('setIDBObjects function inserted.')

        # self.log.debug('Writing IDB data: %s', wa_session_obj)
        self.log.debug('Writing IDB data...')
        self.__driver.execute_script('window.waScript.setAllObjects(arguments[0]);', wa_session_obj)

        self.log.debug('Waiting until all objects are written to IDB...')
        # FIXME: This looks awful. Please find a way to make this look a little better.
        while not self.__driver.execute_script(
                'return (window.waScript.insertDone == window.waScript.jsonObj.length);'):
            time.sleep(1)

    def __verify_profile_name_exists(self, profile_name: str) -> bool:
        self.__refresh_profile_list()
        # NOTE: Is this still required?
        if not isinstance(profile_name, str):
            raise TypeError('The provided profile_name is not a string.')
        if profile_name not in self.__browser_profile_list:
            raise ValueError('The provided profile_name was not found. Make sure the name is correct.')
        else:
            return True

    def __start_session(self, options: Union[c_op.Options, f_op.Options],
                        profile_name: Optional[str] = None, wait_for_login=True) -> NoReturn:
        self.log.debug('Starting browser... [HEADLESS: %s]', str(options.headless))
        if profile_name is None:
            if self.__browser_choice == Browser.CHROME:
                self.__driver = webdriver.Chrome(options=options)
            elif self.__browser_choice == Browser.FIREFOX:
                self.__driver = webdriver.Firefox(options=options)

            self.log.debug('Loading WhatsApp Web...')
            self.__driver.get(self.__URL)

            if wait_for_login:
                self.log.debug('Waiting for login...')
                while not self.verify_profile_object(self.__get_indexed_db_user()):
                    time.sleep(1)
                self.log.debug('Login completed.')
        else:
            if self.__browser_choice == Browser.CHROME:
                options.add_argument('user-data-dir=%s' % os.path.join(self.__browser_user_dir, profile_name))
                self.__driver = webdriver.Chrome(options=options)
            elif self.__browser_choice == Browser.FIREFOX:
                fire_profile = webdriver.FirefoxProfile(os.path.join(self.__browser_user_dir, profile_name))
                self.__driver = webdriver.Firefox(fire_profile, options=options)

            self.log.debug('Loading WhatsApp Web...')
            self.__driver.get(self.__URL)

    def __start_visible_session(self, profile_name: Optional[str] = None, wait_for_login=True) -> NoReturn:
        options = self.__browser_options
        options.headless = False

        if profile_name is not None:
            self.__verify_profile_name_exists(profile_name)
        self.__start_session(options, profile_name, wait_for_login)

    def __start_invisible_session(self, profile_name: Optional[str] = None) -> NoReturn:
        self.__verify_profile_name_exists(profile_name)
        self.__start_session(self.__browser_options, profile_name)

    def __get_profile_storage(self, profile_name: Optional[str] = None) -> list[dict[str, str]]:
        if profile_name is None:
            self.__start_visible_session()
        else:
            self.__verify_profile_name_exists(profile_name)
            self.__start_invisible_session(profile_name)

        indexed_db = self.__get_indexed_db_user()

        self.log.debug("Closing browser...")
        self.__driver.quit()

        return indexed_db

    def __init__(self, browser: Optional[Union[Browser, str]] = None, log_level: Optional[Union[int, str]] = None):
        self.log = logging.getLogger('WaWebSession:SessionHandler')
        log_format = logging.Formatter('%(asctime)s [%(levelname)s] (%(funcName)s): %(message)s')

        log_stream = logging.StreamHandler()
        log_stream.setLevel(logging.DEBUG)
        log_stream.setFormatter(log_format)
        self.log.addHandler(log_stream)

        if log_level:
            self.set_log_level(log_level)
        else:
            self.__log_level = logging.WARNING
            self.log.setLevel(self.__log_level)

        self.__platform = platform.system().lower()
        if self.__platform != 'windows' and self.__platform != 'linux':
            raise OSError('Only Windows and Linux are supported for now.')
        self.log.debug('Detected platform: %s', self.__platform)

        if browser:
            self.set_browser(browser)
        else:
            input_browser_choice = 0
            while input_browser_choice != 1 and input_browser_choice != 2:
                print('1) Chrome\n'
                      '2) Firefox\n')
                input_browser_choice = int(input('Select a browser by choosing a number from the list: '))
            if input_browser_choice == 1:
                self.set_browser(Browser.CHROME)
            elif input_browser_choice == 2:
                self.set_browser(Browser.FIREFOX)

        self.__init_browser()

    def set_log_level(self, new_log_level: Union[int, str]) -> NoReturn:
        possible_level_strings = ['debug', 'info', 'warning', 'error', 'critical']
        possible_level_values = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]

        if isinstance(new_log_level, str):
            new_log_level = new_log_level.lower()
            if new_log_level in possible_level_strings:
                if new_log_level == possible_level_strings[0]:
                    self.__log_level = logging.DEBUG
                elif new_log_level == possible_level_strings[1]:
                    self.__log_level = logging.INFO
                elif new_log_level == possible_level_strings[2]:
                    self.__log_level = logging.WARNING
                elif new_log_level == possible_level_strings[3]:
                    self.__log_level = logging.ERROR
                elif new_log_level == possible_level_strings[4]:
                    self.__log_level = logging.CRITICAL
            else:
                raise ValueError('You can only use one of the following strings to change the log level: %s',
                                 str(possible_level_strings))
        else:
            if new_log_level in possible_level_values:
                self.__log_level = new_log_level
            else:
                # NOTE: Could also be a TypeError
                raise ValueError(
                    'You can only pass a logging level or one of the following string to this function: %s',
                    str(possible_level_strings))

        self.log.setLevel(self.__log_level)

    def set_browser(self, browser: Union[Browser, str]) -> NoReturn:
        if isinstance(browser, str):
            if browser.lower() == 'chrome':
                self.log.debug('Setting browser... [TYPE: %s]', 'Chrome')
                self.__browser_choice = Browser.CHROME
            elif browser.lower() == 'firefox':
                self.log.debug('Setting browser... [TYPE: %s]', 'Firefox')
                self.__browser_choice = Browser.FIREFOX
            else:
                raise ValueError('The specified browser is invalid. Try to use "chrome" or "firefox" instead.')
        elif isinstance(browser, Browser):
            if browser == Browser.CHROME:
                self.log.debug('Setting browser... [TYPE: %s]', 'Chrome')
            elif browser == Browser.FIREFOX:
                self.log.debug('Setting browser... [TYPE: %s]', 'Firefox')
            self.__browser_choice = browser
        else:
            # NOTE: This shouldn't be needed anymore.
            raise TypeError(
                'Browser type invalid. Try to use Browser.CHROME or Browser.FIREFOX instead.'
            )

    # TODO: Think about type aliasing
    def get_active_session(self, use_profile: Optional[Union[list[str], str]] = None, all_profiles=False) -> Union[
        list[dict[str, str]], dict[str, list[dict[str, str]]]
    ]:
        self.log.warning('Make sure the specified browser profile is not being used by another process.')
        profile_storage_dict = {}
        use_profile_list = []
        self.__refresh_profile_list()

        if all_profiles:
            use_profile_list.extend(self.__browser_profile_list)
            self.log.info(
                "Trying to get active sessions for all browser profiles of the selected type..."
            )
        else:
            if use_profile and use_profile not in self.__browser_profile_list:
                raise ValueError('Profile does not exist: %s', use_profile)
            elif use_profile is None:
                return self.__get_profile_storage()
            elif use_profile and use_profile in self.__browser_profile_list:
                use_profile_list.append(use_profile)
            elif isinstance(use_profile, list):
                use_profile_list.extend(use_profile)
            else:
                # NOTE: Should this be a TypeError instead?
                raise ValueError(
                    "Invalid profile provided. Make sure you provided a list of profiles or a profile name."
                )

        for profile in use_profile_list:
            profile_storage_dict[profile] = self.__get_profile_storage(profile)

        return profile_storage_dict

    def create_new_session(self) -> list[dict[str, str]]:
        return self.__get_profile_storage()

    def access_by_obj(self, wa_profile_obj: list[dict[str, str]]) -> NoReturn:
        if not self.verify_profile_object(wa_profile_obj):
            raise TypeError(
                'Invalid profile object provided. '
                'Make sure you only pass one session to this method.'
            )

        self.__start_visible_session(wait_for_login=False)

        self.__set_indexed_db_user(wa_profile_obj)
        self.__set_local_storage(self.convert_idb_to_ls_obj(wa_profile_obj))
        self.log.debug('Reloading WhatsApp Web...')
        self.__driver.refresh()

        self.log.debug('Waiting until the browser window is closed...')
        while True:
            try:
                _ = self.__driver.window_handles
                time.sleep(1)
            except WebDriverException:
                break

    def access_by_file(self, profile_file: str) -> NoReturn:
        profile_file = os.path.normpath(profile_file)

        if os.path.isfile(profile_file):
            self.log.debug('Reading WaSession from file...')
            with open(profile_file, 'r') as file:
                wa_profile_obj = json.load(file)

            self.log.debug('Verifying WaSession object...')
            if not self.verify_profile_object(wa_profile_obj):
                raise TypeError(
                    'There might be multiple profiles stored in this file. '
                    'Make sure you only pass one WaSession file to this method.'
                )

            self.log.debug('WaSession object is valid.')
            self.access_by_obj(wa_profile_obj)

        else:
            raise FileNotFoundError('Make sure you pass a valid WaSession file to this method.')

    def save_profile(self, wa_profile_obj: Union[list[dict[str, str]], dict[str, list[dict[str, str]]]],
                     file_path: str) -> Union[NoReturn, int]:
        file_path = os.path.normpath(file_path)

        if self.verify_profile_object(wa_profile_obj):
            self.log.debug('Saving WaSession object to file...')
            with open(file_path, 'w') as file:
                json.dump(wa_profile_obj, file, indent=2)
        else:
            self.log.debug('Scanning the list for multiple WaSession objects...')
            saved_profiles = 0
            for profile_name in wa_profile_obj.keys():
                profile_storage = wa_profile_obj[profile_name]
                if self.verify_profile_object(profile_storage):
                    self.log.debug('Found a new profile in the list!')
                    single_profile_name = os.path.basename(file_path) + '-' + profile_name
                    self.save_profile(profile_storage, os.path.join(os.path.dirname(file_path), single_profile_name))
                    saved_profiles += 1
            if saved_profiles > 0:
                self.log.debug('Saved %s profile objects as files.', saved_profiles)
                return saved_profiles
            else:
                raise ValueError(
                    'Could not find any profiles in the list. Make sure to specified file path is correct.'
                )


if __name__ == '__main__':
    web = SessionHandler()
    web.set_log_level(logging.DEBUG)
    choice = 0
    while choice != 1 and choice != 2:
        print('1) Save session to file\n'
              '2) View session from a file\n')
        choice = int(input('Select an option from the list: '))

    if choice == 1:
        # TODO: consider adding another option to dump all active sessions for the selected browser type
        web.save_profile(web.get_active_session(), input('Enter a file path for the generated file: '))
        print('File saved.')
    elif choice == 2:
        web.access_by_file(input('Enter a file path: '))
