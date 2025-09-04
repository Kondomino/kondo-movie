#!/bin/bash

# Test Jenna Cooper LA search endpoint
echo "Testing Jenna Cooper LA search endpoint..."

# Test with "CROFT" search term
echo "Searching for 'CROFT'..."
curl -s "https://jennacooperla.com/search/suggest?q=CROFT&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Testing with '337' search term..."
curl -s "https://jennacooperla.com/search/suggest?q=337&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Testing with '337 CROFT' search term..."
curl -s "https://jennacooperla.com/search/suggest?q=337+CROFT&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Testing with '337 N CROFT' search term..."
curl -s "https://jennacooperla.com/search/suggest?q=337+N+CROFT&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Testing with 'NORTH CROFT' search term..."
curl -s "https://jennacooperla.com/search/suggest?q=NORTH+CROFT&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Testing with '337 NORTH CROFT' search term..."
curl -s "https://jennacooperla.com/search/suggest?q=337+NORTH+CROFT&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each" | jq '.'

echo ""
echo "Search tests completed." 