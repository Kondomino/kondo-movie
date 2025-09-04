import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.daniel_gale import DanielGale
from property.address import Address

def test_daniel_gale_enhanced_extraction():
    """Test the enhanced Daniel Gale image extraction with Swiper carousel targeting"""
    
    print("Testing enhanced Daniel Gale image extraction...")
    
    # Test address
    test_address = "14 Shorecliff Place, Great Neck, New York"
    
    try:
        # Create address object
        address = Address(test_address, Address.AddressInputType.AutoComplete)
        
        # Create Daniel Gale engine
        engine = DanielGale()
        
        print(f"Searching for property: {test_address}")
        print(f"Formatted address: {address.formatted_address}")
        print(f"Short formatted address: {address.short_formatted_address}")
        print(f"Place ID: {address.place_id}")
        
        # Get property info
        mls_info = engine.get_property_info(address_obj=address)
        
        if mls_info:
            print(f"\n✅ SUCCESS: Found property data")
            print(f"MLS ID: {mls_info.mls_id}")
            print(f"Price: {mls_info.list_price}")
            print(f"Description: {mls_info.description[:100]}..." if mls_info.description else "No description")
            print(f"Specs: {mls_info.specs}")
            print(f"Images found: {len(mls_info.media_urls)}")
            
            if mls_info.media_urls:
                print(f"\nFirst 3 image URLs:")
                for i, url in enumerate(mls_info.media_urls[:3], 1):
                    print(f"  {i}. {url}")
                
                if len(mls_info.media_urls) > 3:
                    print(f"  ... and {len(mls_info.media_urls) - 3} more images")
            else:
                print("❌ No images found")
                
            return True
        else:
            print("❌ FAILED: No property data found")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_srcset_parsing():
    """Test the srcset parsing helper method"""
    
    print("\nTesting srcset parsing...")
    
    # Test srcset string from Daniel Gale
    test_srcset = "https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=640&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 640w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=750&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 750w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=828&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 828w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=1080&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 1080w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=1200&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 1200w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=1920&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 1920w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=2048&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 2048w, https://img-v2.gtsstatic.net/reno/imagereader.aspx?url=https%3A%2F%2Fm.sothebysrealty.com%2F1194i215%2Fkt719q8ek89gm62tncwdnhw510i215&amp;w=3840&amp;q=75&amp;option=N&amp;permitphotoenlargement=false&amp;fallbackimageurl=https://www.sothebysrealty.com/resources/siteresources/commonresources/images/nophoto/no_image_new.png 3840w"
    
    try:
        engine = DanielGale()
        result = engine._parse_srcset_urls(test_srcset)
        
        if result:
            print(f"✅ SUCCESS: Extracted highest resolution URL")
            print(f"URL: {result}")
            # Check if it's the 3840w version (highest resolution)
            if "w=3840" in result:
                print("✅ CORRECT: Found highest resolution (3840w)")
            else:
                print("❌ INCORRECT: Not the highest resolution")
                return False
        else:
            print("❌ FAILED: No URL extracted from srcset")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("Running enhanced Daniel Gale image extraction tests...\n")
    
    tests = [
        test_srcset_parsing,
        test_daniel_gale_enhanced_extraction
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test failed: {test.__name__}")
            return False
    
    print(f"\n✅ All {passed}/{total} tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 