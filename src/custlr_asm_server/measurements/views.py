# calls the functions related to body measurements based on which url is called in urls.py


from django.shortcuts import render
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.decorators import parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from .serializers import ImageSerializer, MeasurementSerializer
from .models import Image
from rest_framework.views import APIView
from datetime import datetime
from django.core.files import File
import os


# matlab engine api
import matlab.engine
# integrates matlab image processing function into python
def asm_model(image_path, image_instance):
    eng = matlab.engine.start_matlab()
    eng.cd(r'.\matlab')
    try:
        image_landmark, measurement = eng.Custlr_ASM_Server_Front_v2(image_path, nargout=2)

    except Exception as e:
        measurement = -1
        image_landmark = None
        image_instance.delete()
    eng.close()
    return image_landmark, measurement


def split_measurement(measurement_str):
    measurements = []
    temp = measurement_str.split('\n')
    
    for i in range(1,6):
        measurements.append(round(float(temp[i].split(": ")[1]), 2))

    return measurements

# receives a POST request with an image as input and calls the matlab image processing function
# return response of body measurements detected by the matlab function
@api_view(['POST'])
@parser_classes([JSONParser, MultiPartParser])
def image_post(request, format=None):
    uri = request.build_absolute_uri()
    url = uri.rsplit('/', 2)[0]
    if request.FILES:
        data = request.FILES
        image_serializer = ImageSerializer(data=data)

        if image_serializer.is_valid():
            image_instance = image_serializer.save(user=request.user, chest=0, shoulder=0,
                                  arm_size=0, waist=0, arm_length=0, date_created=datetime.now())
            image_path = '..' + str(image_serializer.data['image'])
            # calls the matlab function with the image path sent from client side as input
            image_landmark, measurements = asm_model(image_path, image_instance)

            # matlab image processing function gives error
            if measurements == -1:
                return Response({'error': 'The system is unable to process the image. Please try again.'}, 
                                    status=status.HTTP_422_UNPROCESSABLE_ENTITY)
                                
            cleaned_measurements = split_measurement(measurements)
            image_instance.chest = cleaned_measurements[0]
            image_instance.shoulder = cleaned_measurements[1]
            image_instance.arm_size = cleaned_measurements[2] 
            image_instance.waist = cleaned_measurements[3] 
            image_instance.arm_length = cleaned_measurements[4]
            image_instance.image_landmark.save(os.path.basename(image_landmark), File(open(image_landmark, 'rb')))
            image_instance.save()

            landmark_image_url = url + r'/media/images/' + os.path.basename(image_landmark)
            original_image_url = url + str(image_serializer.data['image'])

            return Response({"chest": cleaned_measurements[0], 
                            "shoulder": cleaned_measurements[1],
                            "arm_size": cleaned_measurements[2],
                            "waist": cleaned_measurements[3],
                            "arm_length": cleaned_measurements[4],
                            "landmark_image_url": landmark_image_url,
                            "original_image_url": original_image_url,
            }, status=status.HTTP_201_CREATED)

        else:
            return Response(image_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    else:
        return Response({'message': 'Image not found'}, status=status.HTTP_400_BAD_REQUEST)


# returns a list of saved image in the database based on user's request
class GetMeasurements(APIView):
    def get(self, request, format=None):
        measurements = Image.objects.filter(user=request.user)
        serializer = MeasurementSerializer(measurements, many=True)
        return Response(serializer.data)


# returns the body measurements and image with landmark detected based on the id of the saved image
class GetMeasurementsById(APIView):
    def get(self, request, id, format=None):
        uri = request.build_absolute_uri()
        domain_url = uri.rsplit('/', 4)[0]

        measurement = Image.objects.get(id=id)
        serializer = MeasurementSerializer(measurement)
        response = serializer.data
        response['image_landmark'] = domain_url + serializer.data['image_landmark']
        response['image'] = domain_url + serializer.data['image']
        return Response(response)
