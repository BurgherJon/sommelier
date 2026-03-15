import os

from google.adk.agents import Agent
from google.adk.tools import google_search


# Google search sub-agent for wine research, date lookup, and shop browsing.
# Uses the cheaper flash model to save costs on searches.
google_search_agent = Agent(
    model=os.getenv('QUICK_AGENT_MODEL'),
    name='google_search_agent',
    description=(
        'A search agent that uses google search to find wine information, '
        'current prices, shop inventories, and real-time information like '
        'today\'s date.'
    ),
    instruction=(
        'Use google search to answer questions about wines, pricing, '
        'availability, and real-time information. When searching for wine '
        'details and pricing, prefer searching wine-searcher.com '
        '(e.g. site:wine-searcher.com [wine name vintage]). '
        'When searching wine shop inventories, use site:ny.eatalyvino.com '
        'or site:italianwinemerchants.com as appropriate.'
    ),
    tools=[google_search],
)
