"""The steps an SDK implements in its steps file. Keep in sync with STEPS.md.

The text of each step is the contract: SDKs mark the function implementing a step
with a comment holding exactly this text.
"""

CREATE_CLIENT = "Given an SDK client for the environment"
GET_ENVIRONMENT_FLAGS = "When the application gets the environment flags"
GET_IDENTITY_FLAGS = 'When the application gets the flags for identity "{identifier}" with traits:'

ALL = [CREATE_CLIENT, GET_ENVIRONMENT_FLAGS, GET_IDENTITY_FLAGS]
