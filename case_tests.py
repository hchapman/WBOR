## Case testing for wbor.org functionality
# Author: Harrison Chapman

import cache

def run():
    runCacheTests()

def runCacheTests():
    runDjCacheTests()

def runDjCacheTests():
    # Put some Djs
    dj1 = cache.putDj(email="tcase",
                      fullname="Test Casington",
                      username="tcase",
                      password="esact")

    dj2 = cache.putDj(email="tcase2@",
                      fullname="Tesla Casey",
                      username="tcase2",
                      password="esac_secret")

    dj3 = cache.putDj(email="ctest@gmail.com",
                      fullname="Chase Testa",
                      username="ctest",
                      password="chest")

    print dj1.to_xml()
    print dj2.to_xml()
    print dj3.to_xml()

    # Alter a Dj's information
    dj2 = cache.putDj(email="teslac", edit_dj=dj2)
    dj2 = cache.putDj(email="teslac@", edit_dj=dj2)
    dj2 = cache.putDj(email="teslac@hotmail.com", edit_dj=dj2)

    dj1 = cache.putDj(fullname="Tess Case", edit_dj=dj1)
    dj1 = cache.putDj(email="tesscase", fullname="Tessa Case", edit_dj=dj1)
    dj1 = cache.putDj(email="tesscase@", fullname="Tessa Case", edit_dj=dj1)

    dj3 = cache.putDj(email="chase", fullname="Chase Case", 
                      password="secret", edit_dj=dj3)
    dj3 = cache.putDj(password="supersecret2", edit_dj=dj3)


    print dj1.to_xml()
    print dj2.to_xml()
    print dj3.to_xml()

    print "--------------------"
    
    print cache.djLogin("ctest", "chest")
    print cache.djLogin("ctest", "secret")
    print cache.djLogin("ctest", "supersecret2")

    # Delete the Djs
    cache.deleteDj(dj1)
    cache.deleteDj(dj2)
    cache.deleteDj(dj3)

    print cache.djLogin("ctest", "supersecret2")
    print cache.djLogin("ctest", "chest")
